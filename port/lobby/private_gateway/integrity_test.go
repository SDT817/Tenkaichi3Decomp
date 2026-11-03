package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type integrityFixture struct {
	public                                         ed25519.PublicKey
	private                                        ed25519.PrivateKey
	manifest, signature, archive, archiveSignature []byte
	files                                          map[string][]byte
}

func makeIntegrityFixture(t *testing.T) integrityFixture {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	f := integrityFixture{public: pub, private: priv, files: map[string][]byte{
		"Tenkaichi3Decomp.exe": []byte("new-game"), "SDL3.dll": []byte("new-sdl"),
		"启动游戏.exe": []byte("new-launcher"), "BT3Connect.exe": []byte("new-bridge"),
		"fonts/中文.ttf": []byte("new-font"), "translations/port/en.json": []byte("translation"),
	}}
	manifest := releaseFiles{Format: 1, Version: "0.17"}
	for name, data := range f.files {
		hash := sha256.Sum256(data)
		manifest.Files = append(manifest.Files, releaseFile{Path: name, Size: int64(len(data)), SHA256: hex.EncodeToString(hash[:])})
	}
	f.manifest, _ = json.Marshal(manifest)
	f.signature = []byte(hex.EncodeToString(ed25519.Sign(priv, f.manifest)) + "\n")
	var output bytes.Buffer
	z := zip.NewWriter(&output)
	for name, data := range f.files {
		w, _ := z.Create("Tenkaichi3Decomp/" + name)
		w.Write(data)
	}
	w, _ := z.Create("Tenkaichi3Decomp/" + integrityManifest)
	w.Write(f.manifest)
	w, _ = z.Create("Tenkaichi3Decomp/" + integrityManifest + ".sig")
	w.Write(f.signature)
	z.Close()
	f.archive = output.Bytes()
	f.archiveSignature = []byte(hex.EncodeToString(ed25519.Sign(priv, f.archive)) + "\n")
	return f
}

func writeFixture(t *testing.T, root string, f integrityFixture) {
	t.Helper()
	for name, data := range f.files {
		p := filepath.Join(root, filepath.FromSlash(name))
		os.MkdirAll(filepath.Dir(p), 0755)
		if err := os.WriteFile(p, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	os.WriteFile(filepath.Join(root, integrityManifest), f.manifest, 0600)
	os.WriteFile(filepath.Join(root, integrityManifest+".sig"), f.signature, 0600)
}

func TestIntegrityOfflineGoodAndPersonalFiles(t *testing.T) {
	f := makeIntegrityFixture(t)
	root := t.TempDir()
	writeFixture(t, root, f)
	for _, name := range []string{"gamedata/disc/SLUS_216.78", "saves/card.ps2", "bt3_settings.txt", "bt3_wii_controls.ini", "fonts/fonts.tsv", "wii_profiles/mine.ini"} {
		p := filepath.Join(root, name)
		os.MkdirAll(filepath.Dir(p), 0755)
		os.WriteFile(p, []byte("personal"), 0600)
		if managedFile(name) {
			t.Fatalf("managed personal file %s", name)
		}
	}
	if err := ensureReleaseFiles(root, &http.Client{}, "http://127.0.0.1:1", "0.17", f.public); err != nil {
		t.Fatal(err)
	}
}

func TestIntegrityRepairAndRetry(t *testing.T) {
	for _, mode := range []string{"missing_dll", "damaged_game", "missing_manifest", "bad_manifest_signature", "truncated_first", "bad_archive_first", "permanent_bad_signature"} {
		t.Run(mode, func(t *testing.T) {
			f := makeIntegrityFixture(t)
			root := t.TempDir()
			writeFixture(t, root, f)
			os.WriteFile(filepath.Join(root, "bt3_settings.txt"), []byte("settings"), 0600)
			goodFont := filepath.Join(root, "fonts", "中文.ttf")
			stamp, _ := os.Stat(goodFont)
			switch mode {
			case "missing_dll":
				os.Remove(filepath.Join(root, "SDL3.dll"))
			case "missing_manifest":
				os.Remove(filepath.Join(root, integrityManifest))
			case "bad_manifest_signature":
				os.WriteFile(filepath.Join(root, integrityManifest+".sig"), []byte("00"), 0600)
			default:
				os.WriteFile(filepath.Join(root, "Tenkaichi3Decomp.exe"), []byte("BAD"), 0600)
			}
			downloads := 0
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if !strings.HasPrefix(r.URL.Path, "/updates/v0.17/") {
					t.Error("wrong repair version")
				}
				if strings.HasSuffix(r.URL.Path, ".sig") {
					if mode == "permanent_bad_signature" {
						w.Write([]byte(strings.Repeat("0", 128)))
						return
					}
					w.Write(f.archiveSignature)
					return
				}
				downloads++
				if mode == "truncated_first" && downloads == 1 {
					w.Header().Set("Content-Length", fmt.Sprint(len(f.archive)))
					w.Write(f.archive[:100])
					return
				}
				if mode == "bad_archive_first" && downloads == 1 {
					w.Write([]byte("damaged-archive"))
					return
				}
				w.Write(f.archive)
			}))
			defer server.Close()
			err := ensureReleaseFiles(root, server.Client(), server.URL, "0.17", f.public)
			if mode == "permanent_bad_signature" {
				if err == nil || downloads != 3 {
					t.Fatalf("must stop after three attempts: %d %v", downloads, err)
				}
				b, _ := os.ReadFile(filepath.Join(root, "Tenkaichi3Decomp.exe"))
				if string(b) != "BAD" {
					t.Fatal("invalid data was installed")
				}
			} else {
				if err != nil {
					t.Fatal(err)
				}
				for name, data := range f.files {
					b, _ := os.ReadFile(filepath.Join(root, name))
					if !bytes.Equal(b, data) {
						t.Fatal(name)
					}
				}
				if (mode == "truncated_first" || mode == "bad_archive_first") && downloads != 2 {
					t.Fatal(downloads)
				}
			}
			fontAfter, _ := os.Stat(goodFont)
			if !fontAfter.ModTime().Equal(stamp.ModTime()) {
				t.Fatal("matching file rewritten")
			}
			settings, _ := os.ReadFile(filepath.Join(root, "bt3_settings.txt"))
			if string(settings) != "settings" {
				t.Fatal("personal file changed")
			}
		})
	}
}

func TestIntegrityRejectsSignedInvalidManifests(t *testing.T) {
	f := makeIntegrityFixture(t)
	for _, name := range []string{"gamedata/disc/file", "../escape", "fonts/../escape", "fonts\\escape", "fonts/a:stream", "bt3_settings.txt", "fonts/fonts.tsv", "fonts/trailing. ", "saves/card.ps2"} {
		var m releaseFiles
		json.Unmarshal(f.manifest, &m)
		m.Files[0].Path = name
		raw, _ := json.Marshal(m)
		sig := []byte(hex.EncodeToString(ed25519.Sign(f.private, raw)))
		if _, err := parseReleaseFiles(raw, sig, "0.17", f.public); err == nil {
			t.Fatalf("accepted %s", name)
		}
	}
	if _, err := parseReleaseFiles(f.manifest, f.signature, "0.18", f.public); err == nil {
		t.Fatal("wrong version accepted")
	}
}

func TestIntegrityRollsBackFailedSwap(t *testing.T) {
	f := makeIntegrityFixture(t)
	root := t.TempDir()
	writeFixture(t, root, f)
	// A nonempty directory blocks replacing the second missing/damaged path.
	os.WriteFile(filepath.Join(root, "Tenkaichi3Decomp.exe"), []byte("old-game"), 0600)
	os.Remove(filepath.Join(root, "SDL3.dll"))
	os.Mkdir(filepath.Join(root, "SDL3.dll"), 0755)
	os.WriteFile(filepath.Join(root, "SDL3.dll", "child"), []byte("keep"), 0600)
	manifest, err := parseReleaseFiles(f.manifest, f.signature, "0.17", f.public)
	if err != nil {
		t.Fatal(err)
	}
	// Ensure the test always replaces the game first, then hits the directory.
	var ordered []releaseFile
	for _, name := range []string{"Tenkaichi3Decomp.exe", "SDL3.dll"} {
		for _, item := range manifest.Files {
			if item.Path == name {
				ordered = append(ordered, item)
			}
		}
	}
	manifest.Files = ordered
	archive, _ := zip.NewReader(bytes.NewReader(f.archive), int64(len(f.archive)))
	if err := installRepair(root, archive, manifest, f.manifest, f.signature); err == nil {
		t.Fatal("directory target must fail")
	}
	game, _ := os.ReadFile(filepath.Join(root, "Tenkaichi3Decomp.exe"))
	if string(game) != "old-game" {
		t.Fatal("previous game not restored")
	}
	if _, err := os.Stat(filepath.Join(root, "SDL3.dll", "child")); err != nil {
		t.Fatal("existing directory modified")
	}
}
