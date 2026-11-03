// Verify the signed release files before loading the game or SDL. Personal
// settings, saves and disc data are deliberately outside the release manifest.
package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const integrityManifest = "bt3_files.json"
const integrityPublicKey = "ce5990d7da701b89b1deb00d15a8adbfe1a09b52cb7bd57b1f36f84abae11de4"
const integrityArchive = "Tenkaichi3Decomp-windows-x64.zip"
const integrityMaxArchive = 256 << 20

// Set by the release build, independently of an untrusted local manifest.
var integrityVersion = "0.17"
var integrityVersionPattern = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+){1,3}$`)

type releaseFile struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type releaseFiles struct {
	Format  int           `json:"format"`
	Version string        `json:"version"`
	Files   []releaseFile `json:"files"`
}

// Only files owned by the release may be restored. Unknown player files stay
// untouched. fonts.tsv is editable and the native updater merges its own rows.
func managedFile(name string) bool {
	if name == "" || strings.ContainsAny(name, "\\:\x00\r\n") || strings.HasPrefix(name, "/") {
		return false
	}
	for _, part := range strings.Split(name, "/") {
		if part == "" || part == "." || part == ".." || strings.TrimRight(part, " .") != part {
			return false
		}
	}
	low := strings.ToLower(name)
	switch low {
	case "tenkaichi3decomp.exe", "tenkaichi3decomp.exe.mem", "tenkaichi3decomp.dat",
		"启动游戏.exe", "bt3connect.exe", "sdl3.dll", "lobby-cn8-build.json", "a11y_es.txt":
		return true
	case "fonts/fonts.tsv":
		return false
	}
	return strings.HasPrefix(low, "fonts/") || strings.HasPrefix(low, "licenses/") ||
		strings.HasPrefix(low, "translations/") || strings.HasPrefix(low, "tbo/ui/")
}

func parseReleaseFiles(raw, signature []byte, version string, public ed25519.PublicKey) (releaseFiles, error) {
	var manifest releaseFiles
	sig, err := hex.DecodeString(strings.TrimSpace(string(signature)))
	if err != nil || len(raw) > 4<<20 || !ed25519.Verify(public, raw, sig) {
		return manifest, errors.New("文件清单签名校验失败")
	}
	if err = json.Unmarshal(raw, &manifest); err != nil {
		return manifest, err
	}
	if manifest.Format != 1 || manifest.Version != version || !integrityVersionPattern.MatchString(version) ||
		len(manifest.Files) == 0 || len(manifest.Files) > 4096 {
		return manifest, errors.New("文件清单版本或格式不正确")
	}
	seen := map[string]bool{}
	var total int64
	for _, file := range manifest.Files {
		lower := strings.ToLower(file.Path)
		hash, err := hex.DecodeString(file.SHA256)
		if !managedFile(file.Path) || seen[lower] || file.Size < 0 || file.Size > integrityMaxArchive || err != nil || len(hash) != sha256.Size {
			return manifest, errors.New("文件清单含有无效、重复或个人文件路径")
		}
		seen[lower] = true
		total += file.Size
	}
	if total > integrityMaxArchive || !seen["tenkaichi3decomp.exe"] || !seen["sdl3.dll"] || !seen["启动游戏.exe"] {
		return manifest, errors.New("文件清单不完整或过大")
	}
	return manifest, nil
}

func releasePath(root, name string) (string, error) {
	path := root
	for _, part := range strings.Split(name, "/") {
		path = filepath.Join(path, part)
		info, err := os.Lstat(path)
		if err == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("不能通过链接修复文件：%s", name)
		}
		if err != nil && !os.IsNotExist(err) {
			return "", err
		}
	}
	return path, nil
}

func fileMatches(path string, expected releaseFile) bool {
	file, err := os.Open(path)
	if err != nil {
		return false
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() != expected.Size {
		return false
	}
	hash := sha256.New()
	_, err = io.Copy(hash, file)
	return err == nil && strings.EqualFold(hex.EncodeToString(hash.Sum(nil)), expected.SHA256)
}

func damagedFiles(root string, manifest releaseFiles) ([]releaseFile, error) {
	var damaged []releaseFile
	for _, file := range manifest.Files {
		path, err := releasePath(root, file.Path)
		if err != nil {
			return nil, err
		}
		if !fileMatches(path, file) {
			damaged = append(damaged, file)
		}
	}
	return damaged, nil
}

func integrityGet(client *http.Client, address string, max int64) ([]byte, error) {
	response, err := client.Get(address)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("下载修复包失败：HTTP %d", response.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, max+1))
	if err != nil || int64(len(raw)) > max {
		return nil, errors.New("修复包下载不完整或过大")
	}
	return raw, nil
}

type repairItem struct {
	target, staged, backup string
	existed, swapped       bool
	expected               releaseFile
}

// Stage and verify all changed files first, then swap, verify read-back, and
// roll back on failure. A running Windows launcher can be renamed, as in the
// native updater. Its old image is removed on a later start if still in use.
func installRepair(root string, archive *zip.Reader, manifest releaseFiles, raw, sig []byte) error {
	bad, err := damagedFiles(root, manifest)
	if err != nil {
		return err
	}
	work, err := releasePath(root, "update")
	if err != nil {
		return err
	}
	if err = os.MkdirAll(work, 0700); err != nil {
		return err
	}
	temporary, err := os.MkdirTemp(work, "file-repair-")
	if err != nil {
		return err
	}
	keepBackups := false
	defer func() {
		if !keepBackups {
			os.RemoveAll(temporary)
		}
	}()
	entries := map[string]*zip.File{}
	for _, file := range archive.File {
		if file.FileInfo().IsDir() {
			continue
		}
		name := strings.TrimPrefix(file.Name, "Tenkaichi3Decomp/")
		if name == file.Name || (!managedFile(name) && name != integrityManifest && name != integrityManifest+".sig") || entries[name] != nil {
			return errors.New("修复包含有无效或重复路径")
		}
		entries[name] = file
	}
	items := make([]repairItem, 0, len(bad)+2)
	for _, file := range bad {
		entry := entries[file.Path]
		if entry == nil || entry.UncompressedSize64 != uint64(file.Size) {
			return fmt.Errorf("修复包缺少文件：%s", file.Path)
		}
		reader, err := entry.Open()
		if err != nil {
			return err
		}
		staged := filepath.Join(temporary, fmt.Sprint(len(items)))
		out, err := os.OpenFile(staged, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			reader.Close()
			return err
		}
		_, err = io.Copy(out, io.LimitReader(reader, file.Size+1))
		reader.Close()
		closeErr := out.Close()
		if err != nil || closeErr != nil || !fileMatches(staged, file) {
			return fmt.Errorf("修复文件校验失败：%s", file.Path)
		}
		target, err := releasePath(root, file.Path)
		if err != nil {
			return err
		}
		items = append(items, repairItem{target: target, staged: staged, expected: file})
	}
	for i, data := range [][]byte{raw, sig} {
		name := integrityManifest
		if i == 1 {
			name += ".sig"
		}
		target, err := releasePath(root, name)
		if err != nil {
			return err
		}
		hash := sha256.Sum256(data)
		expected := releaseFile{Path: name, Size: int64(len(data)), SHA256: hex.EncodeToString(hash[:])}
		staged := filepath.Join(temporary, fmt.Sprint(len(items)))
		if err = os.WriteFile(staged, data, 0600); err != nil {
			return err
		}
		items = append(items, repairItem{target: target, staged: staged, expected: expected})
	}
	rollback := func() {
		for i := len(items) - 1; i >= 0; i-- {
			item := &items[i]
			if item.swapped {
				os.Remove(item.target)
			}
			if item.existed {
				if err := os.Rename(item.backup, item.target); err != nil {
					keepBackups = true
					fmt.Fprintln(os.Stderr, "修复回退失败，保留备份：", item.backup, err)
				}
			}
		}
	}
	for i := range items {
		item := &items[i]
		if err = os.MkdirAll(filepath.Dir(item.target), 0755); err != nil {
			rollback()
			return err
		}
		if info, statErr := os.Stat(item.target); statErr == nil {
			if !info.Mode().IsRegular() {
				rollback()
				return fmt.Errorf("文件位置被目录占用：%s", item.expected.Path)
			}
			item.backup = filepath.Join(temporary, fmt.Sprint(i)+".old")
			if err = os.Rename(item.target, item.backup); err != nil {
				rollback()
				return err
			}
			item.existed = true
		}
		if err = os.Rename(item.staged, item.target); err != nil {
			rollback()
			return err
		}
		item.swapped = true
		if !fileMatches(item.target, item.expected) {
			rollback()
			return fmt.Errorf("安装后的文件校验失败：%s", item.expected.Path)
		}
	}
	os.WriteFile(filepath.Join(temporary, "complete"), []byte("ok\n"), 0600)
	fmt.Fprintf(os.Stderr, "文件修复完成：%d 个程序/资源文件。\n", len(bad))
	return nil
}

func ensureReleaseFiles(root string, client *http.Client, remote, version string, public ed25519.PublicKey) error {
	raw, err := os.ReadFile(filepath.Join(root, integrityManifest))
	sig, sigErr := os.ReadFile(filepath.Join(root, integrityManifest+".sig"))
	if err == nil && sigErr == nil {
		manifest, parseErr := parseReleaseFiles(raw, sig, version, public)
		if parseErr == nil {
			bad, err := damagedFiles(root, manifest)
			if err != nil {
				return err
			}
			if len(bad) == 0 {
				fmt.Fprintf(os.Stderr, "文件校验通过：%d 个文件（版本 %s）。\n", len(manifest.Files), version)
				return nil
			}
			for _, file := range bad {
				fmt.Fprintln(os.Stderr, "文件缺失或校验不符：", file.Path)
			}
		}
	}
	if !integrityVersionPattern.MatchString(version) {
		return errors.New("不能确定修复版本")
	}
	address := strings.TrimRight(remote, "/") + "/updates/v" + version + "/" + integrityArchive
	var last error
	for attempt := 1; attempt <= 3; attempt++ {
		fmt.Fprintf(os.Stderr, "正在重新下载并校验版本 %s（%d/3）……\n", version, attempt)
		last = func() error {
			signature, err := integrityGet(client, address+".sig", 4096)
			if err != nil {
				return err
			}
			data, err := integrityGet(client, address, integrityMaxArchive)
			if err != nil {
				return err
			}
			signatureBytes, err := hex.DecodeString(strings.TrimSpace(string(signature)))
			if err != nil || !ed25519.Verify(public, data, signatureBytes) {
				return errors.New("修复包签名校验失败")
			}
			archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
			if err != nil {
				return err
			}
			read := func(name string, max uint64) ([]byte, error) {
				var found *zip.File
				for _, file := range archive.File {
					if file.Name == "Tenkaichi3Decomp/"+name {
						if found != nil || file.UncompressedSize64 > max {
							return nil, errors.New("修复清单重复或过大")
						}
						found = file
					}
				}
				if found == nil {
					return nil, errors.New("修复包没有文件清单")
				}
				reader, err := found.Open()
				if err != nil {
					return nil, err
				}
				defer reader.Close()
				return io.ReadAll(io.LimitReader(reader, int64(max)+1))
			}
			raw, err := read(integrityManifest, 4<<20)
			if err != nil {
				return err
			}
			sig, err := read(integrityManifest+".sig", 4096)
			if err != nil {
				return err
			}
			manifest, err := parseReleaseFiles(raw, sig, version, public)
			if err != nil {
				return err
			}
			return installRepair(root, archive, manifest, raw, sig)
		}()
		if last == nil {
			return nil
		}
		fmt.Fprintln(os.Stderr, "文件修复未完成：", last)
	}
	return fmt.Errorf("连续三次文件校验/修复失败，请检查网络、磁盘空间或文件占用后重试：%w", last)
}

func verifyGameFiles(root string, remote string, transport *http.Transport) error {
	// A completed repair can leave a still-running Windows launcher backup.
	if work, err := releasePath(root, "update"); err == nil {
		entries, _ := os.ReadDir(work)
		for _, entry := range entries {
			if entry.IsDir() && strings.HasPrefix(entry.Name(), "file-repair-") {
				path := filepath.Join(work, entry.Name())
				if _, err := os.Stat(filepath.Join(path, "complete")); err == nil {
					os.RemoveAll(path)
				}
			}
		}
	}
	public, err := hex.DecodeString(integrityPublicKey)
	if err != nil {
		return err
	}
	client := &http.Client{Transport: transport, Timeout: 3 * time.Minute}
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		return errors.New("修复下载不允许重定向到其它地址")
	}
	return ensureReleaseFiles(root, client, remote, integrityVersion, ed25519.PublicKey(public))
}
