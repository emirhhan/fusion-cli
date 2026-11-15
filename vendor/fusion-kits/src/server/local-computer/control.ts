import { randomUUID } from 'node:crypto';
import type { ComputerControl } from '../../shared/computer-types.js';
import { ConflictError } from './errors.js';

type RequestStatus = 'waiting' | 'taken' | 'released';

/** Tarayıcıyı kimin sürdüğünü izler: varsayılan 'bot'; insan devri istek/al/bırak ile olur. */
export class ControlState {
  private holder: 'bot' | 'human' = 'bot';
  private request?: { id: string; status: RequestStatus };
  private resumeSnapshotRequired = false;

  view(): ComputerControl {
    return {
      holder: this.holder,
      requested: this.request?.status === 'waiting',
      transitioning: false,
      resumeSnapshotRequired: this.resumeSnapshotRequired,
      ...(this.request ? { request: { ...this.request } } : {}),
    };
  }

  requestControl(): ComputerControl {
    if (this.holder === 'human' || this.request?.status === 'waiting')
      return this.view();
    this.request = { id: randomUUID(), status: 'waiting' };
    return this.view();
  }

  private match(requestId: string) {
    if (!this.request || this.request.id !== requestId)
      throw new ConflictError('Kontrol isteği bulunamadı veya eski.');
    return this.request;
  }

  take(requestId: string): ComputerControl {
    const request = this.match(requestId);
    if (request.status === 'released')
      throw new ConflictError('Bu kontrol isteği zaten bırakıldı.');
    this.holder = 'human';
    this.request = { ...request, status: 'taken' };
    return this.view();
  }

  release(requestId: string): ComputerControl {
    const request = this.match(requestId);
    if (this.holder === 'human') {
      this.holder = 'bot';
      // İnsan sayfayı değiştirmiş olabilir; bot önce yeniden bakmalı.
      this.resumeSnapshotRequired = true;
    }
    this.request = { ...request, status: 'released' };
    return this.view();
  }

  /** Bot tarayıcı eylemi yapmadan önce çağrılır. */
  assertBotMayAct(action: string) {
    if (this.holder === 'human' && !['read', 'screenshot'].includes(action))
      throw new ConflictError('Kontrol şu an insanda; bırakılmasını bekle.');
    if (
      this.resumeSnapshotRequired &&
      !['navigate', 'snapshot', 'read', 'screenshot'].includes(action)
    )
      throw new ConflictError(
        'Kontrol geri verildi; önce computer_snapshot ile yenile.',
      );
  }

  assertHumanMayAct() {
    if (this.holder !== 'human')
      throw new ConflictError('İnsan eylemi için önce kontrolü devral.');
  }

  snapshotTaken() {
    this.resumeSnapshotRequired = false;
  }
}
