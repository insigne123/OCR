import type { DocumentFamily, DocumentRecord, StorageProvider } from "@ocr/shared";

export type CreateDocumentInput = {
  file: File;
  documentFamily: DocumentFamily;
  country: string;
  tenantId?: string;
};

export interface DocumentRepository {
  readonly storageProvider: StorageProvider;
  listDocuments(): Promise<DocumentRecord[]>;
  getDocumentById(documentId: string): Promise<DocumentRecord | null>;
  getDocumentByIdInternal(documentId: string): Promise<DocumentRecord | null>;
  createDocumentFromUpload(input: CreateDocumentInput): Promise<DocumentRecord>;
  updateDocument(documentId: string, updater: (document: DocumentRecord) => DocumentRecord): Promise<DocumentRecord | null>;
}
