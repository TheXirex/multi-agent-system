import React, { useState, useRef, useEffect } from 'react';
import { Upload, FileSpreadsheet, X } from 'lucide-react';

interface FileAttachModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (file: File) => void;
  currentFile?: File | null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isValidTabularFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith('.csv') || lower.endsWith('.xlsx') || lower.endsWith('.xls');
}

export const FileAttachModal: React.FC<FileAttachModalProps> = ({
  isOpen,
  onClose,
  onSelectFile,
  currentFile,
}) => {
  if (!isOpen) return null;

  return (
    <FileAttachModalContent
      onClose={onClose}
      onSelectFile={onSelectFile}
      currentFile={currentFile}
    />
  );
};

interface FileAttachModalContentProps {
  onClose: () => void;
  onSelectFile: (file: File) => void;
  currentFile?: File | null;
}

const FileAttachModalContent: React.FC<FileAttachModalContentProps> = ({
  onClose,
  onSelectFile,
  currentFile,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(currentFile || null);
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleFile = (file: File) => {
    if (!isValidTabularFile(file.name)) {
      setErrorMessage('Please select a valid CSV or Excel file (.csv, .xlsx, .xls)');
      return;
    }
    setErrorMessage(null);
    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
    e.target.value = '';
  };

  const handleConfirm = () => {
    if (selectedFile) {
      onSelectFile(selectedFile);
      onClose();
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(3px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '460px',
          backgroundColor: '#212529',
          border: '1px solid #495057',
          borderRadius: '8px',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '14px 18px',
            borderBottom: '1px solid #343a40',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8f9fa' }}>
            Attach Dataset File
          </span>
          <button
            onClick={onClose}
            style={{
              padding: '4px',
              color: '#adb5bd',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleInputChange}
            accept=".csv,.xlsx,.xls"
            style={{ display: 'none' }}
          />

          {/* Drag & Drop Dropzone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${isDragging ? '#f8f9fa' : '#495057'}`,
              backgroundColor: isDragging ? '#343a40' : '#181a1d',
              borderRadius: '6px',
              padding: '28px 20px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              transition: 'background-color 0.15s ease, border-color 0.15s ease',
              textAlign: 'center',
              gap: '10px',
            }}
          >
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '50%',
                backgroundColor: '#2b3035',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ced4da',
              }}
            >
              <Upload size={20} />
            </div>

            <div>
              <p style={{ fontSize: '13px', fontWeight: 600, color: '#f8f9fa', marginBottom: '4px' }}>
                Drag and drop your file here, or browse
              </p>
              <p style={{ fontSize: '11.5px', color: '#adb5bd' }}>
                Supports CSV and Excel files (.csv, .xlsx, .xls)
              </p>
            </div>
          </div>

          {/* Error Message */}
          {errorMessage && (
            <div
              style={{
                fontSize: '12px',
                color: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                border: '1px solid rgba(255, 107, 107, 0.3)',
                padding: '8px 12px',
                borderRadius: '4px',
              }}
            >
              {errorMessage}
            </div>
          )}

          {/* Selected File Card */}
          {selectedFile && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                backgroundColor: '#181a1d',
                border: '1px solid #495057',
                borderRadius: '6px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
                <FileSpreadsheet size={18} color="#f8f9fa" style={{ flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <p
                    style={{
                      fontSize: '12.5px',
                      fontWeight: 600,
                      color: '#f8f9fa',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={selectedFile.name}
                  >
                    {selectedFile.name}
                  </p>
                  <p style={{ fontSize: '11px', color: '#adb5bd' }}>
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedFile(null);
                }}
                style={{
                  padding: '4px',
                  color: '#adb5bd',
                  marginLeft: '8px',
                }}
              >
                <X size={15} />
              </button>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '12px 18px',
            borderTop: '1px solid #343a40',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: '10px',
            backgroundColor: '#1c1f23',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '7px 14px',
              fontSize: '12px',
              fontWeight: 500,
              color: '#ced4da',
              backgroundColor: '#343a40',
              border: '1px solid #495057',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedFile}
            style={{
              padding: '7px 16px',
              fontSize: '12px',
              fontWeight: 600,
              color: selectedFile ? '#212529' : '#6c757d',
              backgroundColor: selectedFile ? '#f8f9fa' : '#343a40',
              border: '1px solid transparent',
              cursor: selectedFile ? 'pointer' : 'not-allowed',
            }}
          >
            Attach File
          </button>
        </div>
      </div>
    </div>
  );
};
