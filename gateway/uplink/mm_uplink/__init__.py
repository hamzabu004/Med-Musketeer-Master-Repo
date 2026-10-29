"""MedMusketeer fixed gateway uplink (Iteration 4).

The gateway's own connection to the cloud's EMQX gateway listener: mutual TLS with the gateway
certificate, the cloud verified by its pinned name. In this first version it reports the gateway's
status and keeps and enforces the wearable revocation list (cloud-backend.md D16); forwarding
wearable messages and the outage backlog plug into the same service later.
"""
