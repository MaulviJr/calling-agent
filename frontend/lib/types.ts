export interface User {
  email: string;
}

export interface Call {
  id: string;
  business_id: string;
  external_id: string | null;
  caller_phone: string;
  direction: string;
  transport: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  status: string;
  outcome: string;
  failure_reason: string;
  summary: string;
  summary_status: string;
}

export interface TranscriptTurn {
  id: string;
  business_id: string;
  call_id: string;
  role: "user" | "assistant";
  text: string;
  delivery: string;
  created_at: string;
}

export interface CallDetail extends Call {
  turns: TranscriptTurn[];
}

export interface Appointment {
  id: string;
  business_id: string;
  call_id: string | null;
  caller_name: string;
  caller_phone: string;
  caller_email: string;
  service_id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  calendar_event_id: string;
  created_at: string;
  updated_at: string;
}

export type MessageStatus = "new" | "reviewed" | "resolved";
export interface Message {
  id: string;
  business_id: string;
  call_id: string | null;
  key: string;
  caller_name: string;
  phone: string;
  content: string;
  urgency: string;
  escalated: number;
  status: MessageStatus;
  created_at: string;
}

export interface Service {
  id: string;
  name: string;
  duration: number;
  active: boolean;
  price: string;
}
export interface BusinessHours {
  weekday: number;
  opens: string;
  closes: string;
}
export interface KnowledgeEntry {
  question: string;
  answer: string;
}
export interface StaffMember {
  id: string;
  name: string;
  role: string;
  qualifications: string[];
  active: boolean;
}
export interface BusinessSettings {
  name: string;
  timezone: string;
  phone: string;
  location: string;
  assistant_name: string;
  greeting: string;
  escalation_number: string;
  voice_id: string;
  buffer_minutes: number;
  minimum_notice_minutes: number;
  maximum_advance_days: number;
  require_email: boolean;
  services: Service[];
  hours: BusinessHours[];
  knowledge: KnowledgeEntry[];
  staff?: StaffMember[];
  escalation_keywords: string[];
  after_hours_message: string;
  cancellation_policy: string;
}

export interface DashboardOverview {
  total_calls: number;
  calls_today: number;
  appointments_booked: number;
  conversion_rate: number;
  average_duration: number;
  unresolved_messages: number;
  escalations: number;
}
export interface CalendarStatus {
  connected: boolean;
  message?: string;
}
export interface CalendarOperation {
  id: string;
  kind: string;
  status: string;
  created_at: string;
}
export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}
export type VoiceEvent =
  | { type: "clear" }
  | { type: "ready"; call_id: string; greeting: string }
  | { type: "reply" | "transcript" | "error"; text: string };
