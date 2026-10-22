export interface Session {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
}

export interface Attachment {
  filename: string;
  content: string;
  file_type?: string;
  size_str?: string;
}

export interface MessageMetadata {
  dataset_id?: number | null;
  dataset_ids?: number[];
  chart_id?: number | null;
  chart_ids?: number[];
  script_id?: number | null;
  code_title?: string | null;
  task_description?: string | null;
  table_name?: string | null;
  sql_description?: string | null;
  attachments?: Attachment[];
  [key: string]: any;
}

export interface Message {
  id?: string;
  session_id?: string;
  role: 'user' | 'assistant';
  content: string;
  metadata?: MessageMetadata;
  created_at?: string;
  // Hydrated artifacts for rendering
  turnIndex?: number;
  datasetData?: DatasetData | null;
  chartsData?: ChartData[];
  pythonScript?: string | null;
  sqlQuery?: string | null;
}

export interface DatasetColumn {
  name: string;
  label?: string;
  type?: string;
}

export interface DatasetData {
  id?: number;
  name?: string;
  columns: DatasetColumn[];
  rows: Record<string, any>[];
  total_rows?: number;
  query?: string;
}

export interface ChartData {
  id?: number;
  title: string;
  chart_type?: string;
  spec: Record<string, any>;
}

export interface ScriptData {
  id?: number;
  script: string;
  language: string;
}

export interface TurnArtifacts {
  turnIndex: number;
  totalTurns: number;
  userQuery?: string;
  messageContent: string;
  metadata: MessageMetadata;
  datasetData?: DatasetData | null;
  chartsData: ChartData[];
  pythonScript?: string | null;
  sqlQuery?: string | null;
}
