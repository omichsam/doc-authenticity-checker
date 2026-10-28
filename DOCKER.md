# Run the document checker with Docker

From this directory, build and start the app with Docker Compose:

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
