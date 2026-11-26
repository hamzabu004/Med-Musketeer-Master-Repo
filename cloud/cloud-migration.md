# Moving the cloud stack to another server

How to move the public deployment (`medmusketeer.site`, an Oracle Cloud VM since 2026-11-04, `docs/decisions/cloud-backend.md` D18) to another provider or VM. The stack is plain Docker Compose, so nothing in it depends on Oracle. What has to move is its state, and what has to change is DNS, the firewall and the deploy settings.

Not yet tried: this is the procedure, not a record of a move. Do a test restore on the new server before the real cutover.

## What has to move

All volumes belong to the compose project `medmusketeer-cloud`, so on the server they are named `medmusketeer-cloud_<name>`.

| State | Where | Move it? |
|---|---|---|
| `cloud/.env` | the server, not tracked | **Yes, always.** ZITADEL's data is sealed with the masterkey in it. A database restored without the same `.env` is unreadable. It also holds the database passwords and the SMTP key. |
| Databases `medmusketeer` and `zitadel` | `postgres-data` | Yes |
| API config and secrets | `mm-config`, `mm-secrets` | Yes |
| ZITADEL bootstrap output | `zitadel-bootstrap` | Yes |
| EMQX server certificate | `emqx-certs` | Yes, or install it again with `scripts/install-emqx-certs.sh` from the CA directory. It is issued for `cloud.medmusketeer.local`, not for a host or address, so it works on any server. |
| Let's Encrypt certificates | `letsencrypt` | Optional. Traefik gets new ones once DNS points at the new server. Copying them avoids waiting on that. |
| EMQX sessions and logs | `emqx-data`, `emqx-log` | No |

Keep the domain the same. ZITADEL keeps its domain from its first start, so changing `ZITADEL_DOMAIN` means starting ZITADEL from scratch (README, "Public deployment").

## 1. Prepare the new server (the old one stays live)

1. Create the VM. Size: the stack uses about 1.9 GB of memory, and the current VM (4 OCPU, 12 GB) has room to spare. Put Docker's data on its own disk, as in README "Server set-up".
2. Note the CPU architecture. The current VM is x86-64. If the new one is ARM (Ampere, Graviton), every image must have an ARM build, and the database must move as a dump (step 3, option B), not as raw files.
3. Do README "Server set-up", adapting the package commands to the new OS: block volume mounted by UUID, Docker Engine with the compose plugin, the systemd drop-in, git.
4. Firewall: open **22, 80, 443 and 8883 only**, in the provider's firewall (security group or list) and in the OS firewall.
5. Check that outbound port 465 is allowed. Some providers block SMTP ports on new accounts, which would stop ZITADEL's password-reset e-mail through Resend.
6. Clone the repository to `~/medmusketeer` the way the deploy expects (a sparse clone of `cloud`, `shared` and `web/dashboard`). Install the deploy key in `~/.ssh/authorized_keys` with its forced command (`cloud/scripts/deploy.sh`, no shell, port or agent forwarding), as in README "Continuous deployment".
7. Join the server to the tailnet for admin access.
8. A day ahead, lower the TTL of the `app`, `api`, `auth` and `mqtt` `A` records to 300 s, so the switch takes effect quickly.

## 2. Freeze the old server

On the old server, in `~/medmusketeer/cloud`:

```bash
docker compose -f compose.yaml -f compose.public.yaml down   # no --volumes
```

From here the site is down and gateways can't upload. Gateways reconnect on their own once the new server answers.

Take a backup to keep, whichever option you use below:

```bash
docker compose -f compose.yaml -f compose.public.yaml up -d --wait postgres
scripts/backup-db.sh ~/migration
docker compose -f compose.yaml -f compose.public.yaml down
```

## 3. Copy the state

### Option A: same architecture: copy the volumes as they are

Exact and simplest. The Postgres image on the new server must be the same version (`timescale/timescaledb:2.31.0-pg18`, from `cloud/postgres/Dockerfile`), which it is when both run the same commit.

On the old server:

```bash
mkdir -p ~/migration && cd ~/migration
for v in postgres-data mm-config mm-secrets zitadel-bootstrap emqx-certs letsencrypt; do
  docker run --rm -v "medmusketeer-cloud_$v:/v:ro" -v "$PWD:/out" alpine \
    tar -C /v -czf "/out/$v.tgz" .
done
cp ~/medmusketeer/cloud/.env ~/migration/env
chmod 600 ~/migration/*
```

Copy it over with `rsync -a ~/migration/ <new-server>:migration/`, or through your own machine.

On the new server, create the volumes through compose first, so they get its labels, then fill them before anything starts:

```bash
cd ~/medmusketeer/cloud
install -m 600 ~/migration/env .env
docker compose -f compose.yaml -f compose.public.yaml create
for v in postgres-data mm-config mm-secrets zitadel-bootstrap emqx-certs letsencrypt; do
  docker run --rm -v "medmusketeer-cloud_$v:/v" -v "$HOME/migration:/in:ro" alpine \
    sh -c "rm -rf /v/* /v/.[!.]* 2>/dev/null; tar -C /v -xzf /in/$v.tgz"
done
```

`tar` keeps file owners and modes, so the key in `emqx-certs` stays at 600 and Postgres keeps ownership of its files.

### Option B: different architecture: restore the dump

Copy `.env` and the `scripts/backup-db.sh` file to the new server. Then start **only Postgres**, so the API's migrations don't run against an empty database first:

```bash
cd ~/medmusketeer/cloud
install -m 600 ~/migration/env .env
docker compose -f compose.yaml -f compose.public.yaml up -d --wait postgres
gunzip -c ~/migration/medmusketeer-*.sql.gz \
  | docker compose -f compose.yaml -f compose.public.yaml exec -T postgres psql -U postgres -d postgres
```

The init script (`postgres/init/010-databases.sh`) has already created the roles and databases, so "already exists" errors for those are expected. Any other error means stop and look. Then install the EMQX certificate with `scripts/install-emqx-certs.sh`. Copy `mm-config`, `mm-secrets` and `zitadel-bootstrap` as in option A; they hold files, not data tied to the CPU.

## 4. Start and switch

1. On the new server: `docker compose -f compose.yaml -f compose.public.yaml up -d --wait --build`. All eight services should be healthy.
2. At the registrar, point the `app`, `api`, `auth` and `mqtt` `A` records at the new address.
3. If `letsencrypt` was not copied, Traefik gets certificates over HTTP-01 once the records resolve. Port 80 must be reachable from outside.

## 5. Point everything else at the new server

- **GitHub secrets** (`production` environment): `DEPLOY_HOST` (new address), `DEPLOY_KNOWN_HOSTS` (the new server's host key, `ssh-keyscan -t ed25519 <host>`, checked against the server's own fingerprint), and `DEPLOY_SSH_KEY` if a new key was made.
- **`.github/workflows/deploy.yml`** connects as `opc`, Oracle Linux's default user. Change it if the new server's user is different (`ubuntu`, `ec2-user`, or your own).
- **Gateway** (`192.168.50.188`): if its uplink uses `mqtt.medmusketeer.site`, the DNS change is enough. If it uses the old address (`138.2.98.23`), change it there.
- **Docs:** update README "Public deployment" and "Server set-up", D18 in `docs/decisions/cloud-backend.md`, the hosting row in `docs/decisions/stack.md`, and add a changelog entry.

## 6. Check

The same checks as the first deployment (`docs/changelog/2026-11-04-01-cloud-on-oracle-vm.md`), plus what the move could break:

- [ ] Valid Let's Encrypt certificates for `app`, `api` and `auth`.
- [ ] From outside, only 22, 80, 443 and 8883 answer. HTTP redirects to HTTPS. `/internal` and `/docs` answer 404.
- [ ] The system admin signs in through ZITADEL and reaches `/system/dashboard` (`/me` 200). This shows the masterkey and the ZITADEL data match.
- [ ] Existing organisations, users, gateways and readings are there.
- [ ] The gateway connects on 8883 with mutual TLS and new readings arrive.
- [ ] "Reset password" sends an e-mail (Resend's dashboard shows it delivered).
- [ ] A manual run of the Deploy workflow succeeds.
- [ ] All services come back healthy after a reboot, with the data volume mounted.

## 7. Roll back or retire

Keep the old server **stopped, not deleted**, for about a week. To roll back, start it again and point DNS back at it. Data written on the new server in the meantime would have to be copied back the same way.

After that week, delete the old VM and its block volume, and delete `~/migration` on both servers and on your own machine. It holds `.env` and the database in clear text.
