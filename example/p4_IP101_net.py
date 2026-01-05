import network

lan = network.LAN(
    mdc=31,
    mdio=52,
    phy_addr=1,
    phy_type=network.PHY_IP101,
    ref_clk=50
)

lan.active(True)
print(lan.ifconfig())


