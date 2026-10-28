# PWD Document Checker

A Streamlit application that lets you upload a scanned or photographed document
image and screen it for possible signs of image editing. It combines a
rule-based image-quality score with a trained convolutional neural network
(CNN) that produces a tampering score and a heat map.

> **Important:** This is an experimental screening aid, not a document
> verification system. A score or heat map cannot prove that a document is
> genuine or forged. Always have a qualified person review the original
> document and any flagged regions. Do not use this model as the sole basis for
> a consequential decision.

## What the app does

1. Accepts an image upload in PNG, JPG/JPEG, WEBP, TIFF, or BMP format.
2. Measures image quality using sharpness, contrast, brightness, and
   resolution. A poor-quality image is flagged because its tampering result
   may be less reliable.
3. Runs the included CNN on overlapping image patches and returns a page-level
   tampering score.
4. Displays a heat map and highlights regions with comparatively high model
   probabilities.
5. Provides a **Forgery lab** for creating a synthetic edit on an uploaded
   page and comparing the model's prediction to the known edit. The edit
   options are field edit, copy-move, splice, and erase.
6. Describes the training and evaluation pipeline in the **How it works** tab.

The lab needs a page with text-like regions to make an edit. If it cannot find
a suitable region, choose another page or generate a new random edit.

## Quick start on Windows

Open PowerShell in this project directory:

```powershell
cd C:\path\to\simple_cnn
```

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run the environment's Python directly in the
commands below instead.

Install the app dependencies and launch Streamlit:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit, usually
[http://localhost:8501](http://localhost:8501).

The requirements install CPU-only PyTorch and torchvision. GPU acceleration
isn't required; inference may take longer on CPU. If you want to use a CUDA
GPU, install a compatible PyTorch/torchvision build for your CUDA setup instead
of the CPU-only versions specified in `requirements.txt`.

## Run with Docker

With Docker Desktop running, start the app from the project directory:

```powershell
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501). Stop the foreground
process with `Ctrl+C`; remove the container and network with:

```powershell
docker compose down
```

If port 8501 is already in use, select a different host port:

```powershell
$env:STREAMLIT_PORT = "8502"
docker compose up --build
```

Then open [http://localhost:8502](http://localhost:8502). See
[DOCKER.md](DOCKER.md) for standalone `docker build` and `docker run`
commands.

The Docker image contains the app and `tamper_cnn.pt`; it excludes the
notebook, dataset, and local reports. The image is configured to run as a
non-root user and has a Streamlit health check.

## Using the application

1. In **Check a document**, upload one of the supported image formats.
2. Review the image-quality score and, if the model loads, the tampering score.
3. Inspect the heat map and highlighted regions. Adjust the sidebar's flag
   threshold or heat-map strength if needed.
4. Treat the results as prompts for human review, not as a final verdict.
5. To try the **Forgery lab**, upload a page first. The uploaded page can then
   be selected in the lab. Alternatively, place JPG sample images in a
   `samples` directory beside `app.py`; that directory is optional and is not
   included in the repository.

The threshold slider changes the page-level verdict. The region overlays use
a fixed probability cutoff and should be interpreted as visual guides.

## Model and training

The application loads the included `tamper_cnn.pt` checkpoint using
`tamper_core.py`. It runs the EfficientNet-B0-based U-Net defined to match the
checkpoint and uses sliding, overlapping patches to keep small details visible
when analyzing a page. Model files are cached while the Streamlit app is
running.

The training pipeline and evaluation are documented in
[PWD_Tamper_CNN_Simple.ipynb](PWD_Tamper_CNN_Simple.ipynb). There is **no
`train.py` script** in this project. The notebook downloads/prepares its
training data and saves the model checkpoint. Its quick mode is intended as a
pipeline smoke test; the notebook recommends a full run for meaningful
evaluation and a GPU for practical training speed. Notebook training has
additional dependencies beyond the app's `requirements.txt`.

The model was trained using genuine-form datasets and synthetic edits. The
training edit types are field edits, copy-move, and splicing. Erasing text is
held out as an unseen edit type during training. These simulated edits may not
represent real-world alterations, and test results on synthetic examples do
not establish accuracy on documents from a particular organization or
population.

## Image handling and privacy

The app accepts raster images only; PDF upload is not supported. The maximum
upload size is configured as 25 MB. The app does not intentionally save
uploaded images to the project directory; the current image is kept in
Streamlit session memory for the lab. When the app is hosted on another
computer or service, uploaded image data is sent to that server for processing.
Only use documents you are authorized to process, and deploy with suitable
privacy and access controls.

## Project layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit user interface and app flow |
| `tamper_core.py` | Model architecture, checkpoint loading, image processing, and inference |
| `tamper_cnn.pt` | Trained model checkpoint used by the app |
| `PWD_Tamper_CNN_Simple.ipynb` | Data preparation, training, and evaluation notebook |
| `requirements.txt` | Python dependencies for running the app |
| `Dockerfile` | Container image definition |
| `compose.yaml` | Docker Compose service and port configuration |
| `DOCKER.md` | Additional Docker run instructions |
| `.streamlit/config.toml` | Streamlit theme and upload-size configuration |
| `training_log.txt` | Saved training log |

The `.gitignore` and `.dockerignore` files exclude local environments, datasets,
reports, and Streamlit secrets.

## Troubleshooting

- **Model could not be loaded:** confirm `tamper_cnn.pt` is next to `app.py`
  and that the app dependencies installed successfully.
- **PyTorch/torchvision import error:** use the project environment and install
  from `requirements.txt`, or install a mutually compatible PyTorch and
  torchvision pair for your hardware.
- **Upload rejected:** check that the image is in a supported format and is
  no larger than 25 MB.
- **The lab says it couldn't create an edit:** select a page with clearly
  visible text or choose a new random edit.
- **Port 8501 is busy:** use the `STREAMLIT_PORT` override in the Docker
  instructions, or stop the other service using that port.

## License and dataset notes

No separate project license is currently included. Review the terms of the
datasets and pretrained components before redistributing the notebook, model,
or derived artifacts. The notebook describes dataset provenance and usage
limitations.
