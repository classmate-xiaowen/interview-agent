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

export interface Evaluation {
  score: number
  covered_points: string[]
  missing_points: string[]
  structure_feedback: string
  expression_feedback: string
  suggestions: string[]
}

export interface InterviewTurn {
  question: string
  question_type: QuestionType
  references: RecordRef[]
  evaluation: Evaluation | null
  ask_followup: boolean
  followup_question: string | null
}

export interface InterviewConfig {
  target_company?: string | null
  target_role?: string | null
  interviewer_style: InterviewerStyle
}

export interface UserProfile {
  skills: string
  years: number
  target_role: string
  target_companies: string[]
  weaknesses: string
  market_context: string
}
