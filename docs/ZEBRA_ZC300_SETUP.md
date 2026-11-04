# Zebra ZC300 setup

The shop printer is **Zebra ZC300 USB Card Printer**. Windows shows it as Idle on port **USB002**. That port means the cable is the connection. The printer has no IP address.

Do not type `USB002`, `192.168.0.217`, or `192.168.0.99` into the website. Those are a port name and the PC's own addresses.

## On the shop PC

1. Open Settings, Bluetooth and devices, Printers and scanners.
2. Select Zebra ZC300 USB Card Printer.
3. Choose Set as default.
4. Open Printer properties, Ports, and confirm the check mark is on USB002.
5. Print a Windows test page from that same screen. A card coming out proves the cable and driver. The website cannot do this test.

## Agent printer name

The agent must be configured with:

```text
Zebra ZC300 USB Card Printer
```

The name has to match the Windows queue exactly. The agent draws a 1011 by 638 pixel card and sends that image at the same size. It will not shrink or stretch it to fit a different page.

## Manual check after the agent is installed

These steps were not run against the physical printer from this repository.

1. Sign in to the website and save a card for a test name.
2. Click Print. The page shows a job id and status `pending`. It must not say the card was printed.
3. On the shop PC, confirm the agent process is running.
4. Within a few polls, the website status becomes `submitted_to_spooler` only after Windows accepts the document.
5. Open the printer queue on the shop PC and confirm the document is there.
6. Confirm whether a plastic card actually came out. Record that separately. Spooler acceptance is not that confirmation.
7. Unplug the USB cable. The agent heartbeat should change to printer unavailable, and a new job should stay pending or return to pending. It must not disappear.
8. Plug the cable back in. The same job may print. If a job is `requires_manual_review`, look in the Windows queue before using Send again.

## What this repository verified

Automated tests render the Keshav Gupta sample to PNG and PDF at 1011 by 638 pixels, with powers `-10.00` and `-11.00`, date `02-11-26`, uppercased name, lens, and retailer, and a QR payload of `J4429`. They do not submit anything to a Zebra.
