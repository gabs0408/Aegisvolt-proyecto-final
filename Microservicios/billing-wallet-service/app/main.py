import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from shared.observability import configure_logging, log_context_middleware

DATABASE_PATH = os.getenv("DATABASE_PATH", "./wallet.db")
ALLOW_TEST_FUNDING = os.getenv("ALLOW_TEST_FUNDING", "false").lower() == "true"
logger = configure_logging("billing-wallet-service")


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _initialize_database() -> None:
    with _database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                fleet_id TEXT PRIMARY KEY,
                balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0),
                currency TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS charges (
                charge_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                fleet_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                charge_id TEXT NOT NULL UNIQUE,
                amount_cents INTEGER NOT NULL
            );
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _initialize_database()
    yield


app = FastAPI(title="Billing Wallet Service", lifespan=lifespan)
app.middleware("http")(log_context_middleware(logger))


class WalletRequest(BaseModel):
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class FundsRequest(BaseModel):
    amount_cents: int = Field(gt=0)


class ChargeRequest(BaseModel):
    fleet_id: str = Field(min_length=1, max_length=128)
    reservation_id: str = Field(min_length=1, max_length=128)
    estimated_amount_cents: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)


class RefundRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)


def _wallet_response(wallet: sqlite3.Row) -> dict[str, object]:
    return {
        "fleet_id": wallet["fleet_id"],
        "balance_cents": wallet["balance_cents"],
        "currency": wallet["currency"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/wallets/{fleet_id}", status_code=201)
def create_wallet(fleet_id: str, request: WalletRequest) -> dict[str, object]:
    with _database() as connection:
        try:
            connection.execute(
                "INSERT INTO wallets (fleet_id, balance_cents, currency) VALUES (?, 0, ?)",
                (fleet_id, request.currency),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Wallet already exists") from error
        wallet = connection.execute("SELECT * FROM wallets WHERE fleet_id = ?", (fleet_id,)).fetchone()
        connection.commit()
    return _wallet_response(wallet)


@app.get("/wallets/{fleet_id}")
def get_wallet(fleet_id: str) -> dict[str, object]:
    with _database() as connection:
        wallet = connection.execute("SELECT * FROM wallets WHERE fleet_id = ?", (fleet_id,)).fetchone()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return _wallet_response(wallet)


@app.post("/wallets/{fleet_id}/funds")
def add_funds(fleet_id: str, request: FundsRequest) -> dict[str, object]:
    if not ALLOW_TEST_FUNDING:
        raise HTTPException(status_code=403, detail="Test funding is disabled")
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE wallets SET balance_cents = balance_cents + ? WHERE fleet_id = ?",
            (request.amount_cents, fleet_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            raise HTTPException(status_code=404, detail="Wallet not found")
        wallet = connection.execute("SELECT * FROM wallets WHERE fleet_id = ?", (fleet_id,)).fetchone()
        connection.commit()
    return _wallet_response(wallet)


@app.post("/charges", status_code=201)
def create_charge(
    request: ChargeRequest,
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, object]:
    correlation_id = request.correlation_id or correlation_header
    if request.correlation_id and correlation_header and request.correlation_id != correlation_header:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request body")
    if correlation_id and request.idempotency_key != correlation_id:
        raise HTTPException(status_code=400, detail="Idempotency key must match correlation ID")

    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM charges WHERE idempotency_key = ?", (request.idempotency_key,)
        ).fetchone()
        if existing is not None:
            same_request = (
                existing["fleet_id"] == request.fleet_id
                and existing["reservation_id"] == request.reservation_id
                and existing["amount_cents"] == request.estimated_amount_cents
            )
            connection.rollback()
            if not same_request:
                raise HTTPException(status_code=409, detail="Idempotency key was used for a different request")
            return {**dict(existing), "correlation_id": correlation_id or request.idempotency_key}

        wallet = connection.execute(
            "SELECT * FROM wallets WHERE fleet_id = ?", (request.fleet_id,)
        ).fetchone()
        if wallet is None:
            connection.rollback()
            raise HTTPException(status_code=404, detail="Wallet not found")
        if wallet["balance_cents"] < request.estimated_amount_cents:
            connection.rollback()
            raise HTTPException(status_code=402, detail="Insufficient wallet funds")

        charge = {
            "charge_id": str(uuid.uuid4()),
            "idempotency_key": request.idempotency_key,
            "fleet_id": request.fleet_id,
            "reservation_id": request.reservation_id,
            "amount_cents": request.estimated_amount_cents,
            "currency": wallet["currency"],
            "status": "charged",
        }
        connection.execute(
            "UPDATE wallets SET balance_cents = balance_cents - ? WHERE fleet_id = ?",
            (request.estimated_amount_cents, request.fleet_id),
        )
        connection.execute(
            """
            INSERT INTO charges
                (charge_id, idempotency_key, fleet_id, reservation_id, amount_cents, currency, status)
            VALUES
                (:charge_id, :idempotency_key, :fleet_id, :reservation_id, :amount_cents, :currency, :status)
            """,
            charge,
        )
        connection.commit()
    return {**charge, "correlation_id": correlation_id or request.idempotency_key}


def _refund_charge(charge_id: str, request: RefundRequest) -> dict[str, object]:
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM refunds WHERE idempotency_key = ?", (request.idempotency_key,)
        ).fetchone()
        if existing is not None:
            connection.rollback()
            if existing["charge_id"] != charge_id:
                raise HTTPException(status_code=409, detail="Idempotency key was used for a different request")
            return {**dict(existing), "correlation_id": request.correlation_id or request.idempotency_key}

        charge = connection.execute(
            "SELECT * FROM charges WHERE charge_id = ?", (charge_id,)
        ).fetchone()
        if charge is None:
            connection.rollback()
            raise HTTPException(status_code=404, detail="Charge not found")
        if charge["status"] != "charged":
            connection.rollback()
            raise HTTPException(status_code=409, detail="Charge has already been refunded")

        refund = {
            "refund_id": str(uuid.uuid4()),
            "idempotency_key": request.idempotency_key,
            "charge_id": charge_id,
            "amount_cents": charge["amount_cents"],
        }
        connection.execute(
            "UPDATE wallets SET balance_cents = balance_cents + ? WHERE fleet_id = ?",
            (charge["amount_cents"], charge["fleet_id"]),
        )
        connection.execute("UPDATE charges SET status = 'refunded' WHERE charge_id = ?", (charge_id,))
        connection.execute(
            "INSERT INTO refunds (refund_id, idempotency_key, charge_id, amount_cents) "
            "VALUES (:refund_id, :idempotency_key, :charge_id, :amount_cents)",
            refund,
        )
        connection.commit()
    return {**refund, "correlation_id": request.correlation_id or request.idempotency_key}


@app.post("/charges/{charge_id}/refunds", status_code=201)
def refund_charge(
    charge_id: str,
    request: RefundRequest,
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, object]:
    if request.correlation_id and correlation_header and request.correlation_id != correlation_header:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request body")
    if correlation_header and request.idempotency_key != correlation_header:
        raise HTTPException(status_code=400, detail="Idempotency key must match correlation ID")
    return _refund_charge(charge_id, request)


@app.post("/correlations/{correlation_id}/refunds", status_code=201)
def refund_by_correlation(
    correlation_id: str,
    request: RefundRequest,
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, object]:
    if request.correlation_id and request.correlation_id != correlation_id:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request body")
    if correlation_header and correlation_header != correlation_id:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request header")
    if request.idempotency_key != correlation_id:
        raise HTTPException(status_code=400, detail="Refund idempotency key must match correlation ID")

    with _database() as connection:
        charge = connection.execute(
            "SELECT charge_id FROM charges WHERE idempotency_key = ?", (correlation_id,)
        ).fetchone()
    if charge is None:
        raise HTTPException(status_code=404, detail="Charge not found for correlation ID")
    return _refund_charge(
        charge["charge_id"],
        request.model_copy(update={"correlation_id": correlation_id}),
    )
