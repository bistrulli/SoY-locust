FROM python:3.10-bullseye

RUN apt update

RUN apt update && \
    apt install -y -qq ffmpeg && \
    apt clean && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://get.docker.com | sh

COPY  . .

RUN pip3 install  --upgrade pip
RUN pip3 install -r requirements.txt

EXPOSE 8081

ENTRYPOINT ["python3"]
CMD ["0_auto-run.py"]
