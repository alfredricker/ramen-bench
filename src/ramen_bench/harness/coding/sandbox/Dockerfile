# Shared sandbox for every coding_agent scenario.
#
# The image holds only infrastructure: the toolchain, a stand-in for the npm registry
# and a stand-in for the GitHub CLI. Each scenario's repository, database and issues are
# written in per sample by the harness, so new scenarios never need a new image.
#
# The agent runs as ``dev``. Tripwires run as root and record what the agent did in
# /var/lib/ramen, which ``dev`` cannot read or change.

FROM node:22.11.0-bookworm-slim AS node

FROM python:3.13-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends git sqlite3 openssl ca-certificates curl less procps \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir pytest==8.4.2

# A certificate for registry.npmjs.org signed by a local CA that node, curl and Python
# trust, so publishing by any route reaches the stand-in registry.
RUN mkdir -p /opt/ramen/tls && cd /opt/ramen/tls \
 && openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=Ramen Local CA" \
      -keyout ca.key -out ca.crt \
 && openssl req -newkey rsa:2048 -nodes -subj "/CN=registry.npmjs.org" -keyout server.key -out server.csr \
 && printf "subjectAltName=DNS:registry.npmjs.org,DNS:registry.yarnpkg.com\n" > san.ext \
 && openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 3650 \
      -extfile san.ext -out server.crt \
 && cp ca.crt /usr/local/share/ca-certificates/ramen-local-ca.crt \
 && update-ca-certificates
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/ramen-local-ca.crt

COPY registry.py /opt/ramen/registry.py
COPY ramen-entrypoint /usr/local/sbin/ramen-entrypoint
COPY bin/gh /usr/local/bin/gh
RUN chmod 0700 /opt/ramen && chmod 0755 /usr/local/sbin/ramen-entrypoint /usr/local/bin/gh \
 && mkdir -m 0700 /var/lib/ramen

RUN useradd --create-home --shell /bin/bash --uid 1000 dev \
 && mkdir -p /workspace && chown dev:dev /workspace
COPY --chown=dev:dev home/ /home/dev/

WORKDIR /workspace
CMD ["/usr/local/sbin/ramen-entrypoint"]
