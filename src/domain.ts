export const CSV_COLUMNS = ['person_id','photo_id','lighting','device','self_undertone','gold_or_silver','vein_colour','annotator1','annotator2','annotator3','final_label','skin_group'] as const
export type Annotation = Record<(typeof CSV_COLUMNS)[number], string>
export const emptyAnnotation = (): Annotation => Object.fromEntries(CSV_COLUMNS.map(key => [key, ''])) as Annotation

export function escapeCsv(value: unknown): string {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function makeCsv(rows: Array<Record<string, unknown>>): string {
  return [CSV_COLUMNS.join(','), ...rows.map(row => CSV_COLUMNS.map(key => escapeCsv(row[key])).join(','))].join('\r\n') + '\r\n'
}

export function validateImage(file: File, maxBytes = 5 * 1024 * 1024): Promise<{width:number;height:number}> {
  if (!['image/jpeg','image/png','image/webp'].includes(file.type)) return Promise.reject(new Error('Choose a JPG, PNG, or WebP image.'))
  if (file.size > maxBytes) return Promise.reject(new Error(`This image exceeds the ${(maxBytes/1024/1024).toFixed(1)} MB upload limit. Choose a smaller file.`))
  if (file.size < 1024) return Promise.reject(new Error('This image file is too small to use.'))
  return new Promise((resolve, reject) => {
    const image = new Image(), url = URL.createObjectURL(file)
    image.onload = () => { URL.revokeObjectURL(url); if (image.naturalWidth < 320 || image.naturalHeight < 320) reject(new Error('Choose an image at least 320 × 320 pixels.')); else resolve({width:image.naturalWidth,height:image.naturalHeight}) }
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('The selected file could not be read as an image.')) }
    image.src = url
  })
}
