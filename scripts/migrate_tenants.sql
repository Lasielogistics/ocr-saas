-- ============================================================
-- Multi-Tenant + RBAC Migration
-- Adds: tenants, users, user_tenant_roles, permissions,
--       role_permissions
-- Adds: tenant_id to all existing TMS tables
-- ============================================================

BEGIN;

-- ── 1. tenants ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    slug          TEXT        NOT NULL UNIQUE,  -- url-safe id, e.g. 'land-air-sea'
    plan          TEXT        NOT NULL DEFAULT 'starter'
                              CHECK (plan IN ('starter','growth','enterprise')),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 2. users ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT        NOT NULL UNIQUE,
    password_hash    TEXT        NOT NULL,
    full_name        TEXT        NOT NULL,
    is_super_admin   BOOLEAN     NOT NULL DEFAULT FALSE,  -- can access all tenants
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 3. user_tenant_roles ────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_tenant_roles (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL CHECK (role IN ('admin','accounting','dispatch','viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, tenant_id)
);

-- ── 4. permissions ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS permissions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    resource    TEXT        NOT NULL,  -- e.g. 'invoices', 'containers', 'users'
    action      TEXT        NOT NULL,  -- e.g. 'read', 'write', 'delete', 'manage'
    description TEXT,
    UNIQUE (resource, action)
);

-- Seed all permissions
INSERT INTO permissions (resource, action, description) VALUES
    ('invoices',    'read',   'View invoices'),
    ('invoices',    'write',  'Create and edit invoices'),
    ('invoices',    'delete', 'Delete invoices'),
    ('clients',     'read',   'View clients'),
    ('clients',     'write',  'Create and edit clients'),
    ('clients',     'delete', 'Delete clients'),
    ('rate_sheets', 'read',   'View rate sheets'),
    ('rate_sheets', 'write',  'Create and edit rate sheets'),
    ('rate_sheets', 'delete', 'Delete rate sheets'),
    ('containers',  'read',   'View containers'),
    ('containers',  'write',  'Create and edit containers'),
    ('containers',  'delete', 'Delete containers'),
    ('appointments','read',   'View appointments'),
    ('appointments','write',  'Create and edit appointments'),
    ('appointments','delete', 'Delete appointments'),
    ('users',       'read',   'View users'),
    ('users',       'write',  'Create and edit users'),
    ('users',       'delete', 'Delete users'),
    ('users',       'manage', 'Manage all user roles'),
    ('reports',     'view',   'View reports'),
    ('settings',    'manage', 'Manage tenant settings'),
    ('audit_log',   'read',   'View audit log')
ON CONFLICT (resource, action) DO NOTHING;

-- ── 5. role_permissions ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS role_permissions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    role          TEXT        NOT NULL CHECK (role IN ('admin','accounting','dispatch','viewer')),
    permission_id UUID        NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE (role, permission_id)
);

-- Seed role → permissions mapping
INSERT INTO role_permissions (role, permission_id)
SELECT 'admin', id FROM permissions
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role, permission_id)
SELECT 'accounting', id FROM permissions
WHERE resource IN ('invoices','clients','rate_sheets','reports')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role, permission_id)
SELECT 'dispatch', id FROM permissions
WHERE resource IN ('containers','appointments')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role, permission_id)
SELECT 'viewer', id FROM permissions
WHERE action IN ('read','view')
ON CONFLICT DO NOTHING;

-- ── 6. Add tenant_id to all existing TMS tables ─────────────
-- Default tenant_id for existing data: Land Air Sea (created below)

-- containers
ALTER TABLE containers ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_containers_tenant ON containers (tenant_id);

-- clients
ALTER TABLE clients ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_clients_tenant ON clients (tenant_id);

-- client_accounts
ALTER TABLE client_accounts ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_client_accounts_tenant ON client_accounts (tenant_id);

-- rate_sheets
ALTER TABLE rate_sheets ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_rate_sheets_tenant ON rate_sheets (tenant_id);

-- invoices
ALTER TABLE invoices ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_invoices_tenant ON invoices (tenant_id);

-- invoice_line_items (no direct tenant_id — belongs to invoice which has tenant_id)
-- invoice_events    (no direct tenant_id — belongs to invoice which has tenant_id)

-- ocr_documents — already has source_system, add tenant_id too
ALTER TABLE ocr_documents ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_ocr_documents_tenant ON ocr_documents (tenant_id);

-- ── 7. updated_at trigger helper (re-apply to new tables) ──
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── 8. Seed Land Air Sea as default tenant ──────────────────
INSERT INTO tenants (id, name, slug, plan) VALUES
    ('00000000-0000-0000-0000-000000000001', 'Land Air Sea Import Export Logistics LLC', 'land-air-sea', 'enterprise')
ON CONFLICT (slug) DO NOTHING;

-- ── 9. Seed admin user (password: tms_admin_2026) ──────────
-- hash generated with bcrypt (pure bcrypt, not passlib)
INSERT INTO users (id, email, password_hash, full_name, is_super_admin) VALUES
    ('00000000-0000-0000-0000-000000000001',
     'admin@landairsea.com',
     '$2b$12$E854pW59aVr3/0.8gsa6o.spBWy1GfTzcncNMThqf1N1Prii.r0e6',
     'System Admin',
     TRUE)
ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash;

-- Give admin the admin role at Land Air Sea
INSERT INTO user_tenant_roles (user_id, tenant_id, role) VALUES
    ('00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'admin')
ON CONFLICT (user_id, tenant_id) DO NOTHING;

-- ── 10. Backfill tenant_id on all existing data ─────────────
UPDATE containers        SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE clients           SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE client_accounts   SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE rate_sheets       SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE invoices          SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE ocr_documents     SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;

-- Make tenant_id NOT NULL now that it's backfilled
ALTER TABLE containers      ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE clients         ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE client_accounts ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE rate_sheets     ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE invoices        ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE ocr_documents   ALTER COLUMN tenant_id SET NOT NULL;

-- ── 11. Audit log table ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL REFERENCES tenants(id),
    user_id     UUID        REFERENCES users(id),
    action      TEXT        NOT NULL,  -- 'login','logout','create_invoice','void_invoice', etc.
    resource    TEXT,        -- 'invoices','clients', etc.
    resource_id UUID,
    details     JSONB,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant ON audit_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user   ON audit_log (user_id);

COMMIT;
