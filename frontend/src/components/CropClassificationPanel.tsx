import { AlertTriangle, Camera, ImagePlus, LoaderCircle, ScanSearch } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ApiError, classifyCropImage } from '../api/client'
import type { CropClassificationResult } from '../api/types'

const MAX_BYTES = 10 * 1024 * 1024

export function CropClassificationPanel() {
  const input = useRef<HTMLInputElement>(null)
  const [crop, setCrop] = useState<'Rice' | 'Maize'>('Rice')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<CropClassificationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const choose = (next: File | null) => {
    setResult(null)
    setFile(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    if (!next) {
      setFile(null)
      setPreview(null)
      return
    }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) {
      setError('Choose a JPEG, PNG or WebP image.')
      return
    }
    if (next.size > MAX_BYTES) {
      setError('Image must be 10 MB or smaller.')
      return
    }
    setError(null)
    setFile(next)
    setPreview(URL.createObjectURL(next))
  }

  const classify = async () => {
    if (!file || loading) return
    const submittedFile = file
    const submittedCrop = crop
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const next = await classifyCropImage(submittedFile, submittedCrop)
      if (file === submittedFile && crop === submittedCrop) setResult(next)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'The classifier could not be reached. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="crop-classifier">
      <section className="crop-intro">
        <ScanSearch size={22} aria-hidden />
        <div>
          <h3>Identify crop health issues</h3>
          <p>Upload a clear close-up of one affected leaf. The model supports Rice and Maize.</p>
        </div>
      </section>

      <fieldset className="crop-choice">
        <legend>Crop in the image</legend>
        {(['Rice', 'Maize'] as const).map((option) => (
          <button key={option} type="button" disabled={loading} aria-pressed={crop === option} onClick={() => { setCrop(option); setResult(null) }}>
            {option}
          </button>
        ))}
      </fieldset>

      <button
        type="button"
        className={`crop-dropzone${preview ? ' has-image' : ''}`}
        disabled={loading}
        onClick={() => input.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0] ?? null) }}
      >
        {preview ? <img src={preview} alt="Selected crop leaf" /> : <ImagePlus size={34} aria-hidden />}
        <span>{file ? file.name : 'Choose or drop a leaf image'}</span>
        <small>JPEG, PNG or WebP, up to 10 MB</small>
      </button>
      <input
        ref={input}
        className="crop-file-input"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => choose(event.target.files?.[0] ?? null)}
      />

      {error && <p className="crop-message crop-error" role="alert"><AlertTriangle size={17} />{error}</p>}

      <button type="button" className="crop-submit" disabled={!file || loading} onClick={classify}>
        {loading ? <LoaderCircle className="crop-spinner" size={19} aria-hidden /> : <Camera size={19} aria-hidden />}
        {loading ? 'Analysing image…' : 'Classify crop image'}
      </button>

      {result && (
        <section className="crop-results" aria-live="polite">
          <div className="crop-results-head">
            <div>
              <span>Most likely</span>
              <h3>{result.predictions[0]?.canonical_class ?? 'No result'}</h3>
            </div>
            {result.predictions[0] && <strong>{Math.round(result.predictions[0].confidence * 100)}%</strong>}
          </div>
          <ol>
            {result.predictions.map((prediction) => (
              <li key={prediction.canonical_class_id}>
                <div>
                  <strong>{prediction.canonical_class}</strong>
                  <span>{prediction.category}</span>
                </div>
                <span>{Math.round(prediction.confidence * 100)}%</span>
                <i style={{ width: `${prediction.confidence * 100}%` }} />
              </li>
            ))}
          </ol>
          {result.needs_expert_review && (
            <p className="crop-message crop-warning">
              <AlertTriangle size={17} />
              The result is uncertain. Ask an agronomist to inspect the crop before acting.
            </p>
          )}
        </section>
      )}

      <p className="crop-disclaimer">This tool does not prescribe pesticides or replace field diagnosis.</p>
    </div>
  )
}
