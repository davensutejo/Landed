# Deploy to a Hong Kong VPS

1. Rent a small VPS (1 vCPU, 1-2 GB RAM, Ubuntu 22.04/24.04) in **Hong Kong**. Hong Kong needs no ICP filing.
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Copy the project to the server without `.env`, `.venv`, `node_modules`, `logs`, `db`.
4. On the server create `.env` next to docker-compose.yml:
       LLM_API_KEY=...
       LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
       LLM_MODEL=glm-4.5-air
5. `docker compose up -d --build`
6. Open `http://<server-ip>/` and check `/api/platforms?market=DE`.
7. From a **mainland network** (phone on mobile data, no VPN) open the page and send a chat message.

HTTPS (optional, needs a domain pointing at the server): run Caddy in front:
    docker run -d --name caddy --network host -v caddy:/data caddy caddy reverse-proxy --from your.domain --to localhost:8000
and change the compose port to `127.0.0.1:8000:8000` and `TRUSTED_PROXY_HOPS` to `"1"` (so rate limiting
sees the visitor's IP that Caddy forwards, not Caddy's own address).

Backups: `docker run --rm -v medici_landed-db:/d -v $PWD:/b alpine tar czf /b/db.tgz -C /d .`
