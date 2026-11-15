export type Status =
  'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
export interface Settings {
  name: string;
  paused: boolean;
  researchAllowed: boolean;
  memoryAllowed: boolean;
}
export type TaskIntent = 'user_requested' | 'proactive_research';
export interface Task {
  intent: TaskIntent;
  id: string;
  prompt: string;
  status: Status;
  intervalSeconds: number | null;
  nextRunAt: number | null;
  createdAt: number;
  updatedAt: number;
  error: string | null;
  lease: string | null;
  leaseUntil: number | null;
}
export interface Source {
  title: string;
  url: string;
  excerpt: string;
}
export interface Result {
  text: string;
  sources: Source[];
  sample: boolean;
  screenshot?: string;
}
export interface Run {
  id: string;
  taskId: string;
  status: string;
  startedAt: number;
  finishedAt: number | null;
  result: Result | null;
  error: string | null;
}
export interface TaskEvent {
  id: number;
  taskId: string;
  runId: string | null;
  text: string;
  createdAt: number;
}
export interface Memory {
  id: string;
  text: string;
  createdAt: number;
}
export interface Detail {
  task: Task;
  runs: Run[];
  events: TaskEvent[];
}
export interface State {
  settings: Settings;
  tasks: Task[];
  memories: Memory[];
  mode: 'sample' | 'live';
  configured: boolean;
}
export type Action = 'run' | 'pause' | 'cancel';
export interface Space {
  id: string;
  name: string;
  description: string;
  createdAt: number;
}
export interface Dot {
  fusionAllowed?: boolean;
  id: string;
  /** Default destination for saved pages, not ownership. */
  spaceId: string;
  spaceIds: string[];
  name: string;
  instructions: string;
  researchAllowed: boolean;
  memoryAllowed: boolean;
  /** Kit'in seçilmiş karakteri (`public/dots/<ad>.png`); yoksa kimlikten türetilir. */
  character?: string | null;
  createdAt: number;
  learningContainerId?: string | null;
  skillDeliveryEnabled?: boolean;
}
export interface Conversation {
  id: string;
  dotId: string;
  ownerId: string;
  title: string;
  createdAt: number;
  /** Frozen at creation; null means this conversation does not participate. */
  learningContainerId?: string | null;
}
export interface CallReceipt {
  anchorMessageId?: string | null;
  id: string;
  threadId: string;
  startedAt: number;
  endedAt: number | null;
  status: 'connecting' | 'active' | 'ended' | 'failed';
  transcript: string;
  error: string | null;
}
export interface SetupStatus {
  intelligence: boolean;
  /** Sohbetlerin tutulduğu yer: dış Intelligence servisi ya da yerel dosya. */
  conversationStore: 'intelligence' | 'local' | 'none';
  model: boolean;
  browser: boolean;
  /** Yerel sesli konuşma (anahtarsız): sohbet hazırsa her zaman kullanılabilir. */
  voice: boolean;
  /** İsteğe bağlı OpenAI Realtime (VOICE_API_KEY + VOICE_MODEL). */
  voiceRealtime: boolean;
  slack: string;
  missing: string[];
}
export interface WorkspaceState {
  conversationRequestProtocol?: 1;
  ownerId?: string;
  spaces: Space[];
  dots: Dot[];
  conversations: Conversation[];
  setup: SetupStatus;
  calls: CallReceipt[];
}
