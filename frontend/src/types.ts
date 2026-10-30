export interface Session {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  last_message?: string | null;
}

export interface Attachment {
  filename: string;
  size_str?: string;
  tables?: string[];
}

export interface MessageMetadata {
  chart_id?: number | null;
  chart_ids?: number[];
  script_id?: number | null;
  sql_script_id?: number | null;
  python_script_id?: number | null;
  sql_query?: string | null;
  code?: string | null;
  code_title?: string | null;
  task_description?: string | null;
  table_names?: string[];
  sql_description?: string | null;
  attachments?: Attachment[];
  [key: string]: any;
}

export interface Message {
  id?: string | number;
  session_id?: string;
  role: 'user' | 'assistant';
  content: string;
  metadata?: MessageMetadata;
  created_at?: string;
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
  id?: string;
  name?: string;
  table_name?: string;
  schema?: string;
  row_count?: number;
  columns: DatasetColumn[];
  rows: Record<string, any>[];
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
  task_description?: string;
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
