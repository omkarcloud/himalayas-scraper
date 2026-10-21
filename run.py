"""Start the Himalayas Scraper API.

    python run.py            # http://localhost:8000
    PORT=9000 python run.py  # another port

Then:  curl "http://localhost:8000/jobs/details?job=netflix/ai-research-scientist-4-5-generative-models-recommender-systems"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)

EXAMPLE = "/jobs/details?job=netflix/ai-research-scientist-4-5-generative-models-recommender-systems"


def main():
    app = bottle.default_app()
    print(f"Himalayas Scraper listening on http://localhost:{config.PORT}/")
    print(f"Try:  curl \"http://localhost:{config.PORT}{EXAMPLE}\"")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="himalayas-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
