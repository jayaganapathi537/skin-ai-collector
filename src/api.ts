import { emptyAnnotation, type Annotation } from './domain'

export type LocalPhoto = {
  photoId: string
  participantId: string
  image?: Blob
  mimeType: string
  fileSize: number
  imageWidth: number
  imageHeight: number
  qualityStatus: 'basic_checks_passed'
  qualityNotes: string[]
  createdAt: string
  reviewStatus: 'pending' | 'approved' | 'rejected'
  rejectionReason: string
  annotation: Annotation
  consentVersion: string
  consentTimestamp: string
  adultConfirmed: boolean
  consentId: string
  idempotencyKey: string
  annotationHistory: Array<{ savedAt: string; annotation: Annotation; reviewStatus: string }>
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'include', ...init })
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try { message = (await response.json()).detail || message } catch { /* use status message */ }
    if (response.status === 401) message = 'Please sign in to the researcher workspace.'
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

type RemotePhoto = Pick<LocalPhoto, 'photoId'|'participantId'|'mimeType'|'fileSize'|'imageWidth'|'imageHeight'|'qualityStatus'|'qualityNotes'|'createdAt'|'reviewStatus'|'rejectionReason'> & {annotation:Partial<Annotation>}

function mapPhoto(p: RemotePhoto): LocalPhoto {
  return {
    photoId: p.photoId, participantId: p.participantId, mimeType: p.mimeType,
    fileSize: p.fileSize, imageWidth: p.imageWidth, imageHeight: p.imageHeight,
    qualityStatus: p.qualityStatus, qualityNotes: p.qualityNotes,
    createdAt: p.createdAt, reviewStatus: p.reviewStatus, rejectionReason: p.rejectionReason,
    annotation: { ...emptyAnnotation(), ...p.annotation }, consentVersion: '', consentTimestamp: '',
    adultConfirmed: true, consentId: '', idempotencyKey: '', annotationHistory: [],
  }
}

export async function saveSubmission(input: {
  photoId: string; consentId: string; consentVersion: string; adultConfirmed: boolean; consentTimestamp?: string;
  image: Blob; mimeType: string; fileSize: number; imageWidth: number; imageHeight: number;
}): Promise<{ photoId: string }> {
  const form = new FormData()
  form.append('image', input.image, `participant-photo.${input.mimeType === 'image/jpeg' ? 'jpg' : input.mimeType.split('/')[1]}`)
  form.append('consent_confirmed', 'true')
  form.append('adult_confirmed', String(input.adultConfirmed))
  form.append('consent_version', input.consentVersion)
  form.append('consent_id', input.consentId)
  const result = await request<{ photo_id?: string; photoId?: string }>('/api/submissions', {
    method: 'POST', headers: { 'Idempotency-Key': input.photoId }, body: form,
  })
  const photoId = result.photoId ?? result.photo_id
  if (!photoId) throw new Error('The photo was uploaded, but the server did not return its reference. Check the researcher dashboard before trying again.')
  return { photoId }
}

export async function listSubmissions(): Promise<LocalPhoto[]> {
  const photos = await request<RemotePhoto[]>('/api/admin/photos')
  return photos.map(mapPhoto)
}

export async function getPhotoImage(photoId: string): Promise<Blob> {
  const response = await fetch(`/api/admin/photos/${encodeURIComponent(photoId)}/image`, { credentials: 'include', cache: 'no-store' })
  if (!response.ok) {
    const message = response.status === 401 ? 'Your researcher session expired. Sign in again.'
      : response.status === 403 ? 'Access to this photo was denied for the current researcher session.'
      : response.status === 404 ? 'This photo is no longer available in the study records.'
      : response.status === 507 ? 'Google Drive authorization needs attention before this photo can be viewed.'
      : 'Photo storage is temporarily unavailable. Try again later.'
    throw new Error(message)
  }
  return response.blob()
}

export async function saveReview(photoId: string, annotation: Annotation, reviewStatus: LocalPhoto['reviewStatus'], rejectionReason: string): Promise<void> {
  await request(`/api/admin/photos/${encodeURIComponent(photoId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotation, reviewStatus, rejectionReason }) })
}

export async function deleteSubmission(photoId: string): Promise<void> {
  await request(`/api/admin/photos/${encodeURIComponent(photoId)}`, { method: 'DELETE' })
}

export async function getResearcherSession(): Promise<{authenticated:boolean;csrf?:string}> {
  return request('/api/admin/me')
}

export async function researcherLogin(username:string,password:string): Promise<void> {
  await request('/api/admin/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username,password}) })
}

export async function researcherLogout(): Promise<void> {
  await request('/api/admin/logout', { method:'POST' })
}

export async function getPublicConfig(): Promise<{consentVersion:string;minimumAge:number;contact:string;retention:string;maxUploadBytes:number;ready:boolean}> {
  return request('/api/public-config')
}

export async function connectDrive(): Promise<string> {
  const result = await request<{authorization_url:string}>('/api/admin/google-drive/authorize', { method:'POST' })
  return result.authorization_url
}

export async function getAdminStatus(): Promise<{drive_connected:boolean;folder_configured:boolean;oauth_configured:boolean;drive_folder_name:string}> { return request('/api/admin/status') }

export async function verifyDrive(): Promise<void> {
  await request('/api/admin/google-drive/verify', { method:'POST' })
}

export async function reconcileUploads(): Promise<{recovered:number;checked:number}> {
  return request('/api/admin/storage/reconcile', { method:'POST' })
}

export async function exportReviewedCsv(): Promise<void> {
  const response = await fetch('/api/admin/export/labels1.csv', { credentials:'include', cache:'no-store' })
  if (!response.ok) throw new Error(response.status === 401 ? 'Please sign in to the researcher workspace.' : 'CSV export failed.')
  const blob = await response.blob(), url = URL.createObjectURL(blob), anchor = document.createElement('a')
  anchor.href = url; anchor.download = 'labels1.csv'; anchor.click(); URL.revokeObjectURL(url)
}
