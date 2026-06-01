-- ============================================================
-- TMS Invoice System Migration
-- Creates: clients, client_accounts, rate_sheets,
--          invoices, invoice_line_items, invoice_events
-- Creates: get_next_invoice_number() function
-- Creates: invoice auto-trigger on ocr_documents verified
-- ============================================================

BEGIN;

-- ── 1. clients ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    client_type   TEXT        NOT NULL CHECK (client_type IN ('direct', 'broker')),
    email         TEXT,
    phone         TEXT,
    address       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name ON clients (name);

-- ── 2. client_accounts ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS client_accounts (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            UUID        NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    account_name         TEXT        NOT NULL,
    account_code         TEXT        NOT NULL,
    billing_contact_email TEXT,
    payment_terms_days   INTEGER     NOT NULL DEFAULT 30,
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_client_accounts_code ON client_accounts (account_code);

-- ── 3. rate_sheets ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rate_sheets (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    client_account_id UUID       NOT NULL REFERENCES client_accounts(id) ON DELETE CASCADE,
    description      TEXT        NOT NULL,
    rate_type        TEXT        NOT NULL CHECK (rate_type IN ('per_container', 'flat', 'per_chassis')),
    amount           NUMERIC(12,2) NOT NULL,
    product_service  TEXT        NOT NULL,  -- matches QuickBooks "Product/Service" column
    effective_from   DATE        NOT NULL,
    effective_to     DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rate_sheets_account ON rate_sheets (client_account_id);

-- ── 4. invoices ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invoices (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number    TEXT        NOT NULL UNIQUE,  -- display: INV-20001, INV-20002 ...
    invoice_number_int INTEGER    NOT NULL UNIQUE,  -- immutable sequential int for ordering
    qb_invoice_num    INTEGER,                      -- preserved QB Ref# (null if new)
    client_account_id UUID        REFERENCES client_accounts(id) ON DELETE SET NULL,
    container_id      UUID        REFERENCES containers(id) ON DELETE SET NULL,
    shipment_type     TEXT        CHECK (shipment_type IN ('import', 'export')),
    status            TEXT        NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft','sent','paid','overdue','voided')),
    issue_date        DATE,
    due_date          DATE,
    subtotal          NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes             TEXT,
    voided_at         TIMESTAMPTZ,
    voided_reason     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_number    ON invoices (invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status    ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_client    ON invoices (client_account_id);
CREATE INDEX IF NOT EXISTS idx_invoices_container  ON invoices (container_id);

-- ── 5. invoice_line_items ──────────────────────────────────
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id    UUID        NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description   TEXT        NOT NULL,
    quantity      NUMERIC(12,4) NOT NULL DEFAULT 1,
    rate          NUMERIC(12,2) NOT NULL,
    amount        NUMERIC(12,2) NOT NULL,
    line_type     TEXT        NOT NULL CHECK (line_type IN ('rate_sheet', 'manual')),
    rate_sheet_id UUID        REFERENCES rate_sheets(id) ON DELETE SET NULL,
    sort_order    INTEGER     NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_line_items_invoice ON invoice_line_items (invoice_id);

-- ── 6. invoice_events (audit trail) ───────────────────────
CREATE TABLE IF NOT EXISTS invoice_events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id  UUID        NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    event_type  TEXT        NOT NULL CHECK (event_type IN ('created','sent','paid','overdue','voided')),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_invoice ON invoice_events (invoice_id);

-- ── 7. Sequence function ───────────────────────────────────
CREATE OR REPLACE FUNCTION get_next_invoice_number()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    next_val INTEGER;
BEGIN
    SELECT COALESCE(MAX(invoice_number_int), 20000) + 1
    INTO next_val
    FROM invoices;

    RETURN next_val;
END;
$$;

-- ── 8. updated_at trigger helper ───────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at to all new tables
CREATE TRIGGER clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER client_accounts_updated_at
    BEFORE UPDATE ON client_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── 9. Invoice auto-trigger on EIR verification ─────────────
-- Fires when: ocr_documents.document_type IN ('container_eir_in','container_eir_out')
--             AND status changes TO 'verified'
-- Creates a draft invoice auto-linked to the container

CREATE OR REPLACE FUNCTION create_invoice_from_eir()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_container_id   UUID;
    v_container_num  TEXT;
    v_shipment_type  TEXT;
    v_account_id     UUID;
    v_invoice_id     UUID;
    v_next_num       INTEGER;
BEGIN
    -- Only fire on status = 'verified' for EIR document types
    IF NEW.status = 'verified'
       AND NEW.document_type IN ('container_eir_in', 'container_eir_out')
       AND (OLD.status IS DISTINCT FROM NEW.status OR OLD.status IS NULL)
    THEN
        -- Resolve container
        IF NEW.container_number IS NOT NULL THEN
            SELECT id INTO v_container_id
            FROM containers
            WHERE container_number = NEW.container_number
            LIMIT 1;

            -- If container doesn't exist, create a minimal one
            IF NOT FOUND THEN
                INSERT INTO containers (container_number)
                VALUES (NEW.container_number)
                RETURNING id INTO v_container_id;
            END IF;
        END IF;

        v_container_num := NEW.container_number;
        v_shipment_type := CASE NEW.document_type
            WHEN 'container_eir_in'  THEN 'import'
            WHEN 'container_eir_out' THEN 'export'
        END;

        -- Try to find a matching client_account by company name on the container
        -- Fall back to null (unassigned invoice, user assigns later)
        SELECT ca.id INTO v_account_id
        FROM client_accounts ca
        JOIN clients c ON c.id = ca.client_id
        WHERE c.name = (
            SELECT "Company" FROM containers WHERE id = v_container_id
        )
          AND ca.is_active = TRUE
        LIMIT 1;

        -- Get next invoice number
        SELECT get_next_invoice_number() INTO v_next_num;

        -- Create the draft invoice
        INSERT INTO invoices (
            invoice_number,
            invoice_number_int,
            client_account_id,
            container_id,
            shipment_type,
            status,
            issue_date,
            due_date
        ) VALUES (
            'INV-' || v_next_num,
            v_next_num,
            v_account_id,
            v_container_id,
            v_shipment_type,
            'draft',
            CURRENT_DATE,
            CURRENT_DATE + INTERVAL '30 days'
        )
        RETURNING id INTO v_invoice_id;

        -- Create audit event
        INSERT INTO invoice_events (invoice_id, event_type, notes)
        VALUES (
            v_invoice_id,
            'created',
            'Auto-created from EIR verification. Container: ' || COALESCE(v_container_num, 'unknown')
        );
    END IF;

    RETURN NEW;
END;
$$;

-- Drop and recreate trigger (idempotent)
DROP TRIGGER IF EXISTS trigger_create_invoice_from_eir ON ocr_documents;

CREATE TRIGGER trigger_create_invoice_from_eir
    AFTER UPDATE ON ocr_documents
    FOR EACH ROW
    WHEN (NEW.status = 'verified')
    EXECUTE FUNCTION create_invoice_from_eir();

COMMIT;
