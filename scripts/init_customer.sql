-- OCR SaaS Customer Schema Template
-- Run this in each new customer's Supabase project

-- Document metadata
CREATE TABLE IF NOT EXISTS ocr_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    document_type TEXT CHECK (document_type IN (
        'pod','invoice','receipt','rate_confirmation','fuel_receipt',
        'scale_ticket','eir','gate_ticket','load_confirmation',
        'terminal_paperwork','appointment_confirmation','container_pickup',
        'container_dropoff','chassis_paperwork','yard_ticket',
        'reference_sheet','unknown'
    )),
    ocr_text TEXT,
    page_count INTEGER DEFAULT 1,
    confidence_score REAL,
    file_hash TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending','queued','processing','completed','failed','review'
    )),
    error_message TEXT,
    webhook_url TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extracted fields (key-value pairs per document)
CREATE TABLE IF NOT EXISTS ocr_extracted_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES ocr_documents(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    field_value TEXT,
    confidence REAL,
    page_number INTEGER,
    bbox JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ocr_documents_job_id ON ocr_documents(job_id);
CREATE INDEX IF NOT EXISTS idx_ocr_documents_status ON ocr_documents(status);
CREATE INDEX IF NOT EXISTS idx_ocr_documents_created_at ON ocr_documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ocr_extracted_fields_doc_id ON ocr_extracted_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_extracted_fields_name ON ocr_extracted_fields(field_name);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ocr_documents_updated_at ON ocr_documents;
CREATE TRIGGER ocr_documents_updated_at
    BEFORE UPDATE ON ocr_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Row Level Security
ALTER TABLE ocr_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_extracted_fields ENABLE ROW LEVEL SECURITY;

-- Policy: service role has full access (worker uses service role key)
DROP POLICY IF EXISTS "Service role full access" ON ocr_documents;
CREATE POLICY "Service role full access" ON ocr_documents
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Service role full access" ON ocr_extracted_fields;
CREATE POLICY "Service role full access" ON ocr_extracted_fields
    FOR ALL USING (auth.role() = 'service_role');

-- Grant permissions
GRANT ALL ON ocr_documents TO service_role;
GRANT ALL ON ocr_extracted_fields TO service_role;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO service_role;
