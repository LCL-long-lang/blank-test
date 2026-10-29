/** 对应 backend/app/common/schemas.py 的 SchemaOut（GET /api/schema） */
export interface SchemaColumn {
  name: string
  type: string
  description: string
}

export interface SchemaTable {
  name: string
  label: string
  description: string
  row_count: number
  columns: SchemaColumn[]
}

export interface SchemaOut {
  tables: SchemaTable[]
  examples: string[]
}
