FROM rust:1.82-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.toml
COPY src src
RUN cargo build --release

FROM debian:bookworm-slim
RUN useradd --create-home --uid 10001 gateway
COPY --from=build /src/target/release/creation-security-gateway /usr/local/bin/creation-security-gateway
USER gateway
ENTRYPOINT ["/usr/local/bin/creation-security-gateway"]
