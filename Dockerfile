FROM chetan1111/botasaurus:chrome-151

ENV PYTHONUNBUFFERED=1
# Never open debug prompts/devtools on crash.
ENV ENV=production

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

RUN mkdir app
WORKDIR /app
COPY . /app

EXPOSE 8000

# The image ships real Google Chrome + Xvfb. Jobs, companies, salaries and
# statistics are plain HTTP; Chrome only starts to clear Cloudflare once for
# the talent search pages, then those run over plain HTTP too.
CMD ["python", "run.py"]
