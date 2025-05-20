# Use Python 3.13 as the base image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . /app
RUN apt-get update && apt-get install -y curl
# Install dependencies manually including gunicorn
RUN pip install --no-cache-dir \
    Flask \
    Jinja2 \
    bs4 \
    Werkzeug \
    click \
    numpy \
    openpyxl \
    pandas \
    pytz \
    requests \
    six \
    gunicorn

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run gunicorn when the container launches
# Assuming your Flask app instance in wii-games.py is named 'app'
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wii-games:app"]