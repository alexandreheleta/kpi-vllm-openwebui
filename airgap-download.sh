#!/bin/bash
#
# Download everything needed for airgapped deployment
# Run this on a machine with internet access
#
set -e

# Change to script directory (fixes Docker Desktop path issues on Windows)
cd "$(dirname "$0")"

echo "=== Airgap Download Script ==="
echo "Working directory: $(pwd)"
echo ""

# Check required files exist
REQUIRED_DIRS=("exporter" "grafana" "otel-config")
REQUIRED_FILES=("exporter/Dockerfile" "exporter/requirements.txt" "exporter/exporter.py" ".env.example" "supervision-airgap.yml")

for dir in "${REQUIRED_DIRS[@]}"; do
    if [[ ! -d "${dir}" ]]; then
        echo "ERROR: Required directory '${dir}' not found"
        exit 1
    fi
done

for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${file}" ]]; then
        echo "ERROR: Required file '${file}' not found"
        exit 1
    fi
done

echo "All required files found."
echo ""

# Create output directory
mkdir -p airgap-bundle

# Images to download
OTEL_IMAGE="docker.io/grafana/otel-lgtm:0.15.0"
EXPORTER_IMAGE="metrics-exporter:latest"

echo "=== Pulling otel-lgtm image ==="
docker pull "${OTEL_IMAGE}"

echo ""
echo "=== Building metrics-exporter image ==="
docker build -t "${EXPORTER_IMAGE}" ./exporter

echo ""
echo "=== Saving images to tar files ==="
docker save -o airgap-bundle/otel-lgtm.tar "${OTEL_IMAGE}"
docker save -o airgap-bundle/metrics-exporter.tar "${EXPORTER_IMAGE}"

echo ""
echo "=== Copying configuration files ==="
cp supervision-airgap.yml airgap-bundle/
cp .env.example airgap-bundle/.env
cp -r grafana airgap-bundle/
cp -r otel-config airgap-bundle/

echo ""
echo "=== Bundle complete ==="
echo ""
echo "Contents of airgap-bundle/:"
ls -lh airgap-bundle/
echo ""
echo "Total size:"
du -sh airgap-bundle/
echo ""
echo "To deploy on airgapped machine:"
echo "  1. Copy the airgap-bundle/ directory to the target machine"
echo "  2. cd airgap-bundle"
echo "  3. docker load -i otel-lgtm.tar"
echo "  4. docker load -i metrics-exporter.tar"
echo "  5. Edit .env with your settings"
echo "  6. docker-compose -f supervision-airgap.yml up -d"
