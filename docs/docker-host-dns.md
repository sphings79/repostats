# Name resolution fails inside containers (docker01)

## Symptom

Every collection run ended with `Fehler` and the note
`[Errno -3] Temporary failure in name resolution`. No repositories were
collected. The same happened to every other container on the host.

## Cause

On docker01 (Docker 29.8.0) the host resolves names fine, but containers got
no upstream DNS server. Inside any container:

```
nameserver 127.0.0.11
# NO EXTERNAL NAMESERVERS DEFINED
```

The host's `/etc/resolv.conf` is written by dhcpcd and contains a link-local
IPv6 entry with a zone id:

```
nameserver 192.168.181.223
nameserver fe80::a270:9b65:859c:84ef%eno1
```

Docker most likely discards the whole file because of that second line. This
is a suspicion, not proven: the fix below worked, the parser was not
inspected. Rebooting the host did not help.

## Fix

Give the Docker daemon its own DNS server instead of letting it read the
host's `resolv.conf`. `/etc/docker/daemon.json` on docker01:

```json
{"dns": ["192.168.181.223"]}
```

Then restart Docker (this restarts all containers):

```bash
sudo systemctl restart docker
```

Applied on 2026-10-30. The container's `resolv.conf` now reads
`# Overrides: [nameservers]` and `api.github.com` resolves.

## Check

```bash
docker exec repostats python -c "import socket; print(socket.getaddrinfo('api.github.com', 443)[0][4])"
```

## Notes

- Containers created before the change only pick it up after a restart or
  re-creation. A daemon restart covered all running ones.
- If the DNS server `192.168.181.223` changes, update `daemon.json` too.
- Per-service alternative in `compose.yaml`: `dns: [192.168.181.223]`.
  Not used, because the problem affects the whole host.
