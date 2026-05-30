FROM golang:1.26.3-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/radar-control ./cmd/server

FROM alpine:3.22

RUN adduser -D -u 10001 appuser

WORKDIR /app
COPY --from=builder /out/radar-control /usr/local/bin/radar-control

USER appuser

EXPOSE 8080

CMD ["radar-control"]
