# Run the document checker with Docker

## Run locally

From the project directory, build and start the app with Docker Compose:

```powershell
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501). Stop the app with
`Ctrl+C`; run `docker compose down` to remove its container.

If port 8501 is already in use, choose another host port. In PowerShell:

```powershell
$env:STREAMLIT_PORT = "8502"
docker compose up --build
```

Then open [http://localhost:8502](http://localhost:8502).

The image includes the saved `tamper_cnn.pt` model and the Streamlit app. It
does not include the training notebook or dataset; document images are
processed in memory when uploaded.

To build and run without Compose:

```powershell
docker build -t pwd-document-checker .
docker run --rm -p 8501:8501 pwd-document-checker
```

## Deploy on your own Linux server

The server needs Git, Docker Engine, and the Docker Compose plugin. For a new
deployment, connect to the server over SSH and run:

```bash
git clone https://github.com/omichsam/doc-authenticity-checker.git
cd doc-authenticity-checker
docker compose up -d --build
```

Open `http://SERVER_IP:8501` if the server firewall allows port 8501. To check
the container and its startup logs:

```bash
docker compose ps
docker compose logs -f
```

To deploy later changes, run these commands from the cloned project directory:

```bash
git pull --ff-only origin main
docker compose up -d --build
```

The `--ff-only` option avoids creating an accidental merge commit on the
server. To stop the service:

```bash
docker compose down
```

The app currently has **no sign-in or access control**. Do not expose port
8501 to the public internet as-is, especially because users may upload
sensitive documents. Restrict access with the server firewall or a VPN, or put
the app behind an authenticated HTTPS reverse proxy before sharing it
publicly. Check applicable privacy and security requirements before deploying
real documents.
