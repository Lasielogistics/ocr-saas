# TMS-Related GitHub Repositories

## 1. Notifications/Email

| Repo | Stars | License | Description | TMS Use Case |
|------|-------|---------|-------------|--------------|
| *No results found* | - | - | - | Driver SMS alerts, shipment status notifications, delivery confirmation emails |

> Search: `email-notification+sms-gateway+notification-service`

---

## 2. Reporting/Excel

| Repo | Stars | License | Description | TMS Use Case |
|------|-------|---------|-------------|--------------|
| Payroll-Engine/PayrollEngine.Document | 1 | MIT | NuGet library for report generation and data export — PDF output via FastReport templates (.frx) and Excel export (.xlsx) from DataSet with typed cells, filters, and auto-sized columns. | Export shipment reports, invoices, delivery manifests to Excel/PDF |

> Search: `excel-export+report-generation+data-export`

---

## 3. Multi-tenancy/RBAC

| Repo | Stars | License | Description | TMS Use Case |
|------|-------|---------|-------------|--------------|
| alihamzahq/laravel-multi-tenant-saas-starter | 0 | N/A | Multi-tenant SaaS starter kit using Laravel 12, React, and Inertia.js. Built to demonstrate scalable architecture, tenant isolation, and clean full-stack development practices. | Tenant isolation for multi-customer TMS, carrier-specific data partitions |

> Search: `multi-tenancy+saas-architecture+tenant`

---

## 4. Rate Limiting/API Gateway

| Repo | Stars | License | Description | TMS Use Case |
|------|-------|---------|-------------|--------------|
| EmmyAnieDev/Job-Microservice | 22 | N/A | A cloud-native microservices job application API with Laravel auth service, Flask job listings, and FastAPI applications service. Features: Redis used for storing JTI for token revocation, Traefik API Gateway with JWT authentication, rate limiting, circuit breaker, and comprehensive middleware. | Protect external API endpoints, throttle carrier API calls |
| efemirik/guardian-api | 2 | N/A | A high-performance, Redis-backed Rate Limiting middleware and API Gateway written in Go. | API rate limiting for third-party integrations |
| goholic/api-gateway | 1 | N/A | A production-ready Middleware Proxy built with FastAPI and Redis to demonstrate scalable backend patterns: Distributed Tracing, Rate Limiting, and Traffic Shaping. | FastAPI-based API gateway for TMS microservices |
| adityawdubey/partner-api-gateway | 1 | N/A | API Gateway managing external partner access to internal services with authentication, rate limiting, and audit logging. Built with FastAPI, SQLModel, and SQLite. | Partner/customer API access management |
| rajveer100704/gogate-api-gateway | 1 | Apache-2.0 | GoGate is a high-performance API Gateway built in Go, featuring config-driven routing, a plugin-based middleware system, and support for HTTP and gRPC. It includes Redis-backed rate limiting, circuit breaker, retries, OpenTelemetry tracing, and benchmarking for resilient, low-latency microservice communication. | High-performance gateway for carrier API integrations |
| sahasourav17/goGateway | 1 | MIT | A high-performance, cloud-native API Gateway built in Go. It uses Consul for dynamic, zero-downtime route configuration and provides centralized middleware for authentication, rate limiting, and circuit breaking. | Dynamic routing for TMS service mesh |
| ItPohgero/simple-gateway | 1 | MIT | Simple Gateway – A lightweight API gateway built with Bun + Hono. Provides fast routing, flexible middleware (auth, rate limiting, logging), and easy proxying to multiple microservices. | Lightweight gateway for route optimization services |
| n0l3r/limitron | 1 | MIT | limitron is a Go library providing flexible and efficient rate limiting algorithms with support for multiple storage backends (in-memory and Redis). | Token bucket/fixed window rate limiting library |
| ashutosh-lodha/api-gateway-rate-limiter | 1 | N/A | Distributed API Gateway implementing Redis-based rate limiting, async request logging via Redis Streams, background worker ingestion into MySQL, usage analytics APIs, and horizontally scalable middleware architecture using Go and Docker. | Distributed rate limiting across TMS instances |
| durga1534/rate-limiter-api-gateway | 1 | N/A | A backend service with authentication, API key generation, and request rate limiting. Users can register, get secure access tokens, and call protected APIs with enforced usage limits. | API key-based throttling for carrier webhooks |
| idirdev/api-gateway-lite | 0 | MIT | Lightweight API gateway — routing, rate limiting, auth middleware, and request proxying | Minimal gateway for internal TMS services |
| aryankhatri02/api-gateway-dotnet | 0 | N/A | Production-style API Gateway built with ASP.NET Core featuring request routing, authentication, rate limiting, and logging using middleware. | .NET-based TMS gateway alternative |
| Niksinikhilesh045/api-gateway-fastapi | 0 | MIT | Built a production-grade REST API Gateway with JWT authentication, Redis-backed rate limiting (token bucket), and middleware-driven request handling. | FastAPI + Redis rate limiting reference |

> Search: `api-gateway+rate-limiting+middleware`

## Label/Shipping Generation (zpl+label+printer)

| Repo | Description | Stars | License |
|------|-------------|-------|---------|
| BinaryKits/BinaryKits.Zpl | .NET libraries for creating Zebra labels, generates ZPL data | 393 | MIT |
| michaelrsweet/lprint | A Label Printer Application | 330 | Apache-2.0 |
| porrey/Virtual-ZPL-Printer | Virtual Zebra Label Printer for testing ZPL bar code labels | 311 | LGPL-3.0 |
| robgridley/zebra | PHP ZPL builder, image conversion and Zebra network client | 226 | MIT |
| w3blogfr/zebra-zpl | Library for generating ZPL commands for Zebra printers (Java) | 203 | NOASSERTION |
| teynon/ZPL-Label-Designer | Javascript/Web Based designer for ZPL printers | 199 | MIT |
| mrothenbuecher/zpl-rest | REST-API to send ZPL/ZPLII to Zebra label printers | 116 | MIT |
| ABurbank70/BISG-Shipping-Label | Generate shipping labels for ZPL printers | 1 | MIT |

## Authentication/RBAC/Permissions (casbin+permission+RBAC)

| Repo | Description | Stars | License |
|------|-------------|-------|---------|
| apache/casbin | Apache Casbin: access control library (ACL, RBAC, ABAC) | 20041 | Apache-2.0 |
| apache/casbin-node | Casbin for Node.js/Browser | 2889 | Apache-2.0 |
| apache/casbin-jcasbin | Casbin for Java | 2630 | Apache-2.0 |
| apache/casbin-pycasbin | Casbin for Python | 1727 | Apache-2.0 |
| php-casbin/php-casbin | Casbin for PHP | 1325 | Apache-2.0 |
| apache/casbin-Casbin.NET | Casbin for .NET (C#) | 1311 | Apache-2.0 |
| apache/casbin-rs | Casbin for Rust | 1097 | Apache-2.0 |

## Email Notifications (transactional-email+sendgrid+postmark)

| Repo | Description | Stars | License |
| ------|-------------|-------|---------|
| productdevbook/unemail | Unified email API across 18 providers (SMTP, Resend, SES, Postmark, SendGrid, Mailgun) | 184 | MIT |
| quartzy/courier | Domain-driven transactional email library in PHP | 23 | NOASSERTION |
| steve-lebleu/cliam | Agnostic transactional email sending in Node.js | 14 | AGPL-3.0 |
| aaurelions/octomailer | Universal Node.js library for sending transactional emails | 3 | ISC |

