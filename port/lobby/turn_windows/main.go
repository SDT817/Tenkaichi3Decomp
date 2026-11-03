// Windows-native wrapper around Pion's existing TURN server and REST auth.
// No game protocol, synchronization or rollback code is implemented here.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"

	"github.com/pion/logging"
	"github.com/pion/turn/v4"
)

type config struct {
	Listen   string `json:"listen"`
	PublicIP string `json:"public_ip"`
	RelayIP  string `json:"relay_ip"`
	Secret   string `json:"secret"`
	MinPort  uint16 `json:"min_port"`
	MaxPort  uint16 `json:"max_port"`
}

func main() {
	path := flag.String("config", "turn.json", "configuration file")
	flag.Parse()
	data, err := os.ReadFile(*path)
	if err != nil {
		log.Fatal("Cannot read TURN configuration")
	}
	c := config{Listen: "0.0.0.0:3478", RelayIP: "0.0.0.0", MinPort: 49160, MaxPort: 49259}
	if json.Unmarshal(data, &c) != nil || len(c.Secret) < 32 || net.ParseIP(c.PublicIP).To4() == nil || c.MinPort < 1024 || c.MaxPort < c.MinPort {
		log.Fatal("Invalid TURN configuration")
	}
	listener, err := net.ListenPacket("udp4", c.Listen)
	if err != nil {
		log.Fatal(err)
	}
	logger := logging.NewDefaultLoggerFactory()
	logger.DefaultLogLevel = logging.LogLevelError
	server, err := turn.NewServer(turn.ServerConfig{
		Realm:         "BT3_PRIVATE_LOBBY",
		LoggerFactory: logger,
		AuthHandler:   turn.LongTermTURNRESTAuthHandler(c.Secret, logger.NewLogger("bt3-turn")),
		PacketConnConfigs: []turn.PacketConnConfig{{
			PacketConn: listener,
			RelayAddressGenerator: &turn.RelayAddressGeneratorPortRange{
				RelayAddress: net.ParseIP(c.PublicIP), Address: c.RelayIP, MinPort: c.MinPort, MaxPort: c.MaxPort,
			},
			// An authenticated game only needs public IPv4 peers. Localhost is
			// enabled solely by the explicit loopback test configuration.
			PermissionHandler: func(_ net.Addr, peer net.IP) bool {
				if net.ParseIP(c.PublicIP).IsLoopback() { return peer.IsLoopback() }
				return peer.To4() != nil && peer.IsGlobalUnicast() && !peer.IsPrivate()
			},
		}},
	})
	if err != nil {
		listener.Close()
		log.Fatal(err)
	}
	fmt.Printf("BT3 TURN relay ready on %s (Pion TURN v4.1.3; standard UDP TURN)\n", listener.LocalAddr())
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	<-stop
	server.Close()
}
