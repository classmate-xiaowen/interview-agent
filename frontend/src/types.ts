export type QuestionType = 'behavioral' | 'technical' | 'pressure' | 'follow_up'
export type InterviewerStyle = 'pressure' | 'gentle' | 'deep'
export type RecordResult = 'passed' | 'failed' | 'pending'

export interface InterviewRecordCreate {
  question: string
  my_answer?: string | null
  reference_answer?: string | null
  company?: string | null
  department?: string | null
  interviewer_mindset?: string[]
  difficulty?: number | null
  result?: RecordResult | null
  note?: string | null
}

export interface InterviewRecordRead extends InterviewRecordCreate {
  id: string
  created_at: string
}

/** AI 解析出的单道题（仅内容字段，不含元数据） */
export interface ParsedQuestion {
  question: string
  my_answer?: string | null
  reference_answer?: string | null
  note?: string | null
}

/** AI 题库解析结果 */
export interface ParsedQuestionBank {
  questions: ParsedQuestion[]
}

export interface RecordRef {
  record_id: string
  snippet: string
}

export interface CorrectedAnswer {
  corrected_text: string
  change_points: string[]
}

export interface Evaluation {
  score: number
  overall_level: '优秀' | '良好' | '合格' | '待提升' | '不合格' | null
  covered_points: string[]
  missing_points: string[]
  structure_feedback: string
  expression_feedback: string
  suggestions: string[]
  corrected_answer: CorrectedAnswer | null
}

export interface InterviewTurn {
  question: string
  question_type: QuestionType
  references: RecordRef[]
  evaluation: Evaluation | null
  ask_followup: boolean
  followup_question: string | null
  is_summary?: boolean
}

export interface InterviewConfig {
  target_company?: string | null
  target_role?: string | null
  target_jd?: string | null
  salary?: string | null
  rounds?: number | null
  max_questions?: number | null
  interviewer_style: InterviewerStyle
}

export interface UserProfile {
  skills: string
  years: number
  target_role: string
  target_companies: string[]
  weaknesses: string
  market_context: string
  resume_text?: string | null
}

export type PiiCategory = 'name' | 'phone' | 'email' | 'id_card' | 'company' | 'address' | 'social'

export interface PiiItem {
  category: PiiCategory
  text: string
  start: number
  end: number
}

export interface MaskSelection {
  start: number
  end: number
  category: PiiCategory
  action: 'mask' | 'placeholder' | 'ignore'
}

export interface DetectResponse {
  items: PiiItem[]
}

export interface MaskResponse {
  masked_text: string
  applied: PiiItem[]
}

/** 会话列表项（侧栏展示） */
export interface ChatSessionMeta {
  session_id: string
  title: string
  interviewer_style: InterviewerStyle
  target_company: string | null
  target_role: string | null
  target_jd: string | null
  salary: string | null
  rounds: number | null
  max_questions: number | null
  created_at: string
  updated_at: string
}

/** 会话历史消息 */
export interface ChatHistoryMessage {
  role: 'user' | 'assistant'
  content: string
  turn: InterviewTurn | null
  created_at: string
}

/** 成本聚合：单维度一行（模型 / 阶段 / 日期 / 会话） */
export interface CostBreakdownRow {
  key: string
  tokens_in: number
  tokens_out: number
  turns: number
  cost: number
}

/** 成本聚合总览 */
export interface CostStats {
  totals: {
    tokens_in: number
    tokens_out: number
    turns: number
    sessions: number
    cost: number
  }
  by_model: CostBreakdownRow[]
  by_stage: CostBreakdownRow[]
  by_day: CostBreakdownRow[]
  top_sessions: CostBreakdownRow[]
  recommendations: string[]
  currency: string
}
