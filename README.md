# Document authenticity checker

A Streamlit interface for a saved CNN model that screens document images for
possible alterations and displays a heat map of suspicious regions. The
project also includes an image-quality score and a lab for trying synthetic
edits.

## Run locally

Install the requirements:

```powershell
python -m pip install -r requirements.txt
```

Start the app:

```powershell
python -m streamlit run app.py
```

## Run with Docker

```powershell
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501). See [DOCKER.md](DOCKER.md)
for alternative Docker commands and changing the host port.

## Model and data

The app loads the included `tamper_cnn.pt` checkpoint. Training data and
intermediate reports are not included in the Docker image or Git repository.
The notebook documents the training pipeline and evaluation.

## Important limitation

This model is an experimental screening aid trained using synthetic edits.
It cannot establish that a document is genuine or forged. Results require
human review, and the model should be evaluated on appropriate, consented
documents before any consequential use.
