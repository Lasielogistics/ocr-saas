-- Add manually_reviewed column to ocr_documents
ALTER TABLE ocr_documents ADD COLUMN IF NOT EXISTS manually_reviewed BOOLEAN DEFAULT FALSE;
