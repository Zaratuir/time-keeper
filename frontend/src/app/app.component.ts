import { CommonModule } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { interval, Subscription } from 'rxjs';

interface Task {
  id: number;
  name: string;
  notes: string;
  created_at: string;
  total_seconds: number;
  running: boolean;
}

interface Session {
  id: number;
  task_id: number;
  started_at: string;
  stopped_at: string | null;
  duration_seconds: number | null;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <main class="shell">
      <header class="topbar">
        <a class="brand" href="/" aria-label="Time Keeper home"><span class="brand-mark">◷</span> timekeeper</a>
        <span class="top-note"><span class="live-dot"></span> YOUR TIME, IN FOCUS</span>
      </header>

      <section class="intro">
        <p class="eyebrow">MAKE EVERY MINUTE COUNT</p>
        <h1>Good work takes <em>time.</em></h1>
        <p class="subtitle">Choose a task, start the clock, and stay in your flow.</p>
      </section>

      <section class="summary" aria-label="Time summary">
        <div class="summary-label">TOTAL TRACKED</div>
        <div class="summary-value">{{ formatDuration(totalSeconds) }}<span class="summary-unit"> logged</span></div>
        <div class="summary-meta"><span class="live-dot" [class.invisible-dot]="!activeTask"></span>{{ activeTask ? 'Timer running · ' + activeTask.name : 'Ready when you are' }}</div>
        <div class="summary-decoration">{{ formatHours(totalSeconds) }}<span>h</span></div>
      </section>

      <section class="tasks-section">
        <div class="section-heading">
          <div><p class="eyebrow">YOUR WORKSPACE</p><h2>Tasks <span class="count">{{ tasks.length }}</span></h2></div>
          <button class="add-button" type="button" (click)="showForm = !showForm">{{ showForm ? '× Close' : '+ New task' }}</button>
        </div>

        <form class="new-task" *ngIf="showForm" (ngSubmit)="createTask()">
          <div class="form-fields"><input name="name" [(ngModel)]="newName" placeholder="What are you working on?" maxlength="120" required autofocus>
            <input name="notes" [(ngModel)]="newNotes" placeholder="A short note (optional)" maxlength="1000"></div>
          <button class="primary-button" type="submit" [disabled]="!newName.trim() || saving">{{ saving ? 'Adding…' : 'Add task' }}</button>
        </form>

        <p class="notice error" *ngIf="error">{{ error }}</p>
        <div class="loading" *ngIf="loading">Loading your tasks…</div>
        <div class="empty-state" *ngIf="!loading && tasks.length === 0">
          <span class="empty-icon">✳</span><h3>A little room to begin.</h3><p>Add your first task and give it your full attention.</p>
          <button class="primary-button" type="button" (click)="showForm = true">Create your first task</button>
        </div>

        <article class="task-card" *ngFor="let task of tasks; trackBy: trackTask">
          <div class="task-main"><span class="task-status" [class.active]="task.running"></span>
            <div class="task-copy"><h3>{{ task.name }}</h3><p *ngIf="task.notes">{{ task.notes }}</p></div>
            <div class="task-time"><strong>{{ formatDuration(task.total_seconds) }}</strong><span>TIME SPENT</span></div>
            <button class="timer-button" [class.stop-button]="task.running" type="button" (click)="toggleTimer(task)" [attr.aria-label]="task.running ? 'Stop timer for ' + task.name : 'Start timer for ' + task.name">
              <span>{{ task.running ? 'Ⅱ' : '▶' }}</span>{{ task.running ? 'Stop' : 'Start' }}
            </button>
            <button class="delete-button" type="button" (click)="deleteTask(task)" [attr.aria-label]="'Delete ' + task.name" title="Delete task">×</button>
          </div>
        </article>
        <p class="footer-note" *ngIf="tasks.length">A steady pace is still progress. Keep going.</p>
      </section>
      <footer>TIME KEEPER <span>·</span> A QUIETER WAY TO TRACK YOUR DAY</footer>
    </main>
  `,
  styleUrl: './app.component.css',
})
export class AppComponent implements OnInit, OnDestroy {
  tasks: Task[] = [];
  showForm = false;
  newName = '';
  newNotes = '';
  loading = true;
  saving = false;
  error = '';
  private ticker?: Subscription;
  private refreshTicker?: Subscription;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    this.loadTasks();
    this.ticker = interval(1000).subscribe(() => this.tick());
    this.refreshTicker = interval(15000).subscribe(() => this.loadTasks(false));
  }

  ngOnDestroy(): void { this.ticker?.unsubscribe(); this.refreshTicker?.unsubscribe(); }

  get totalSeconds(): number { return this.tasks.reduce((sum, task) => sum + task.total_seconds, 0); }
  get activeTask(): Task | undefined { return this.tasks.find((task) => task.running); }
  trackTask(_: number, task: Task): number { return task.id; }

  loadTasks(showLoading = true): void {
    if (showLoading) this.loading = true;
    this.http.get<Task[]>('/api/tasks').subscribe({
      next: (tasks) => { this.tasks = tasks; this.loading = false; this.error = ''; },
      error: () => { this.loading = false; this.error = 'Could not reach the time keeper API. Check that the services are running.'; },
    });
  }

  createTask(): void {
    if (!this.newName.trim() || this.saving) return;
    this.saving = true;
    this.http.post<Task>('/api/tasks', { name: this.newName.trim(), notes: this.newNotes.trim() }).subscribe({
      next: () => { this.newName = ''; this.newNotes = ''; this.showForm = false; this.saving = false; this.loadTasks(false); },
      error: (error: HttpErrorResponse) => { this.saving = false; this.error = this.messageFor(error); },
    });
  }

  toggleTimer(task: Task): void {
    if (task.running) {
      const activeSession = this.sessionsFor(task.id);
      activeSession.subscribe({
        next: (sessions) => {
          const running = sessions.find((session) => !session.stopped_at);
          if (!running) { this.loadTasks(false); return; }
          this.http.post<Session>(`/api/sessions/${running.id}/stop`, {}).subscribe({
            next: () => this.loadTasks(false), error: (error) => this.error = this.messageFor(error),
          });
        }, error: (error) => this.error = this.messageFor(error),
      });
      return;
    }
    this.http.post<Session>(`/api/tasks/${task.id}/start`, {}).subscribe({
      next: () => this.loadTasks(false), error: (error) => this.error = this.messageFor(error),
    });
  }

  private sessionsFor(taskId: number) { return this.http.get<Session[]>(`/api/sessions?task_id=${taskId}`); }

  deleteTask(task: Task): void {
    if (task.running || !window.confirm(`Delete “${task.name}” and its time history?`)) return;
    this.http.delete(`/api/tasks/${task.id}`).subscribe({
      next: () => this.loadTasks(false), error: (error) => this.error = this.messageFor(error),
    });
  }

  private tick(): void { this.tasks = this.tasks.map((task) => task.running ? { ...task, total_seconds: task.total_seconds + 1 } : task); }
  formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const remaining = (seconds % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}:${remaining}`;
  }
  formatHours(seconds: number): string { return (seconds / 3600).toFixed(1); }
  private messageFor(error: HttpErrorResponse): string {
    return error.error?.detail ?? 'That action could not be completed. Please try again.';
  }
}
