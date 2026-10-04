# time 0.3.55 in Cargo.lock declares rust-version = 1.88.0 and uses edition 2024.\nFROM rust:1.88-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src src
RUN cargo build --release --locked

FROM debian:bookworm-slim
RUN useradd --create-home --uid 10001 gateway
COPY --from=build /src/target/release/creation-security-gateway /usr/local/bin/creation-security-gateway
RUN mkdir -p /var/lib/stf-gateway && chown gateway:gateway /var/lib/stf-gateway
USER gateway
ENTRYPOINT ["/usr/local/bin/creation-security-gateway"]
