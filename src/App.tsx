import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Camera, Check, CheckCircle2, ChevronRight, Copy, Download, HardDrive, HeartHandshake, ImagePlus, Sun, UploadCloud, UserRound, X } from 'lucide-react'
import { CSV_COLUMNS, emptyAnnotation, validateImage, type Annotation } from './domain'
import { connectDrive, deleteSubmission, exportReviewedCsv, getAdminStatus, getPhotoImage, getPublicConfig, getResearcherSession, listSubmissions, reconcileUploads, researcherLogin, researcherLogout, saveReview, saveSubmission, verifyDrive, type LocalPhoto } from './api'

function Header() {
  return <header className="header"><Link to="/" className="brand"><span className="brandmark"><Sun size={20}/></span><span>Skin AI <b>Data Collector</b></span></Link><nav><a href="/#study">About the study</a><Link className="nav-link" to="/dashboard">Researcher review <HardDrive size={14}/></Link></nav></header>
}

function Footer() {
  return <footer className="footer"><div className="footer-mark"><Sun size={16}/> Skin AI Data Collector</div><span>Photos are sent to the study owner’s private Google Drive after consent.</span><span>For privacy or deletion requests, use the study contact shown in the consent information.</span></footer>
}

function Home() {
  const [consent, setConsent] = useState(false)
  const [config,setConfig]=useState<{consentVersion:string;minimumAge:number;contact:string;retention:string;maxUploadBytes:number;ready:boolean}>({consentVersion:'',minimumAge:18,contact:'',retention:'',maxUploadBytes:5*1024*1024,ready:false})
  useEffect(()=>{void getPublicConfig().then(setConfig).catch(()=>{})},[])
  return <><Header/><div className="local-banner"><HardDrive size={15}/> Private study storage · your photo is sent to the study owner’s Google Drive after consent.</div><main>
    <section className="hero"><div className="hero-copy"><div className="eyebrow"><span className="eyebrow-dot"/> VOLUNTEER RESEARCH STUDY</div><h1>Help us understand<br/>colour, <i>your way.</i></h1><p>We’re collecting volunteer facial photographs to support research into personalized clothing colour recommendations using skin tone and undertone analysis.</p><button className="button primary" onClick={()=>setConsent(true)} disabled={!config.ready}>Participate in the study <ArrowRight size={17}/></button>{!config.ready&&<div className="hero-note">Participant collection is not open yet. The study owner must finish the storage and consent setup first.</div>}<div className="hero-note"><HardDrive size={14}/> Only the study owner and authorized researchers can access submitted photos.</div></div><div className="hero-art" role="img" aria-label="Dimensional illustration representing the volunteer research study"><div className="sun-arc arc-one"/><div className="sun-arc arc-two"/><div className="portrait"><div className="portrait-head"><div className="hair"/><div className="face"><span className="eye left"/><span className="eye right"/><span className="nose"/><span className="mouth"/></div><div className="neck"/><div className="shirt"/></div></div><span className="art-label">A small contribution,<br/>a thoughtful study.</span></div></section>
    <section className="stats"><div><span className="stat-icon"><HeartHandshake size={18}/></span><p><b>Voluntary by design</b><br/>Take part only if you feel comfortable.</p></div><div><span className="stat-icon"><HardDrive size={18}/></span><p><b>Private study storage</b><br/>Researchers access photos through a sign-in protected workspace.</p></div><div><span className="stat-icon"><Camera size={18}/></span><p><b>About two minutes</b><br/>One photo, a few simple steps.</p></div></section>
    <section className="study" id="study"><div className="section-title"><span className="eyebrow">THE STUDY</span><h2>What your participation means</h2></div><div className="study-grid"><article><span>01</span><h3>Why we’re collecting photos</h3><p>This study explores skin-tone characteristics and clothing-colour recommendations. Volunteer photographs help researchers create a manually labelled research dataset.</p></article><article><span>02</span><h3>How your photo is used</h3><p>Photos are uploaded to a private Google Drive folder controlled by the study owner. Only the researcher workspace can retrieve them; no public Drive links are created.</p></article><article><span>03</span><h3>Your choice, your control</h3><p>Participation is voluntary. You may withdraw by contacting the study owner, who can remove the photo and its associated record.</p></article></div><div className="privacy-strip"><HardDrive size={19}/><span><b>Know where your photo goes.</b> Photographs are identifiable personal data. They are private in the study's Google Drive and available to authorized researchers only. <button className="text-button" onClick={()=>setConsent(true)}>Read participant information <ChevronRight size={15}/></button></span></div></section>
  </main><Footer/>{consent&&<ConsentModal config={config} onCancel={()=>setConsent(false)}/>}</>
}

function ConsentModal({config,onCancel}:{config:{consentVersion:string;minimumAge:number;contact:string;retention:string;maxUploadBytes:number;ready:boolean};onCancel:()=>void}) {
  const [agreed,setAgreed]=useState(false),[ageConfirmed,setAgeConfirmed]=useState(false)
  const dialogRef=useRef<HTMLElement>(null)
  const navigate=useNavigate()
  const contactConfigured=Boolean(config.contact.trim())&&!/update this contact|your email|@example\.(com|org|test)/i.test(config.contact)
  const retentionConfigured=Boolean(config.retention.trim())&&config.retention.trim()!=="Photos are retained until a researcher deletes them or the study retention period ends."&&!/\b(todo|tbd|replace this|update this)\b/i.test(config.retention)
  useEffect(()=>{
    const previous=document.activeElement instanceof HTMLElement?document.activeElement:null
    const dialog=dialogRef.current
    dialog?.focus()
    const onKeyDown=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();onCancel();return}
      if(event.key!=='Tab'||!dialog)return
      const controls=Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),[href],select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])'))
      if(!controls.length){event.preventDefault();return}
      const first=controls[0],last=controls[controls.length-1]
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    }
    document.addEventListener('keydown',onKeyDown)
    return()=>{document.removeEventListener('keydown',onKeyDown);previous?.focus()}
  },[onCancel])
  return <div className="overlay" role="presentation"><section ref={dialogRef} tabIndex={-1} className="modal" role="dialog" aria-modal="true" aria-labelledby="consent-title" aria-describedby="consent-intro"><button className="icon-button modal-close" onClick={onCancel} aria-label="Close"><X size={19}/></button><div className="modal-icon"><HardDrive size={22}/></div><div className="eyebrow">BEFORE YOU BEGIN</div><h2 id="consent-title">Participant information & consent</h2><p id="consent-intro" className="modal-intro">Please read this information before deciding whether to take part.</p><div className="consent-copy"><p>This project studies skin-tone characteristics and clothing-colour recommendations. If you participate, one facial photograph is uploaded to the study owner's private Google Drive. A random participant reference, consent record, basic image metadata, and researcher annotations are stored in a PostgreSQL database hosted by Neon. The application is hosted by Vercel.</p><p>The photo is not published or shared through a public link. Authorized researchers can retrieve it through the password-protected researcher workspace. Google Drive, Neon, and Vercel process data to provide the study's storage and hosting services. Photographs can identify you, so they are treated as personal data.</p><p><b>Retention:</b> {retentionConfigured?config.retention:'The study retention period has not been configured. Collection is not open.'} {retentionConfigured&&'The researcher can delete your submission and associated record. Separately exported files are not removed automatically.'}</p><p>Taking part is voluntary. You may stop before uploading a photo. This study accepts adults aged {config.minimumAge} and older; photographs of minors must not be submitted.</p><p>The service applies temporary per-network request limits to deter abuse. The app database does not store network addresses; the hosting provider may keep its own connection logs.</p><p><b>Withdrawal or deletion:</b> {contactConfigured?<>contact the study owner at {config.contact} to request withdrawal and deletion.</>:'The study contact has not been configured. Collection is not open.'}</p><p>Consent version {config.consentVersion}.</p></div>{!config.ready&&<p className="inline-error" role="status">Participant collection is currently closed. You cannot continue until study information and storage checks are complete.</p>}<label className="check-row"><input type="checkbox" checked={ageConfirmed} onChange={e=>setAgeConfirmed(e.target.checked)} disabled={!config.ready}/><span>I confirm that I am at least {config.minimumAge} years old.</span></label><label className="check-row"><input type="checkbox" checked={agreed} onChange={e=>setAgreed(e.target.checked)} disabled={!config.ready}/><span>I have read the information above and voluntarily agree to participate.</span></label><div className="modal-actions"><button className="button secondary" onClick={onCancel}>Close</button><button className="button primary" disabled={!config.ready||!agreed||!ageConfirmed} onClick={()=>navigate('/capture',{state:{consent:true,consentVersion:config.consentVersion,consentedAt:new Date().toISOString(),consentId:crypto.randomUUID(),idempotencyKey:crypto.randomUUID(),adultConfirmed:true}})}>Agree & continue <ArrowRight size={16}/></button></div></section></div>
}

type ConsentState={consent?:boolean;consentVersion?:string;consentedAt?:string;consentId?:string;idempotencyKey?:string;adultConfirmed?:boolean}
function Capture() {
  const navigate=useNavigate(), location=useLocation(), video=useRef<HTMLVideoElement>(null), stream=useRef<MediaStream|null>(null)
  const info=location.state as ConsentState|null
  const [mode,setMode]=useState<'choose'|'camera'|'preview'|'saving'|'done'>('choose'),[photo,setPhoto]=useState<File|null>(null),[url,setUrl]=useState(''),[error,setError]=useState(''),[reference,setReference]=useState(''),[busy,setBusy]=useState(false),[copied,setCopied]=useState(false),[dimensions,setDimensions]=useState<{width:number;height:number}|null>(null)
  const [maxUploadBytes,setMaxUploadBytes]=useState(5*1024*1024)
  const cleanup=()=>{stream.current?.getTracks().forEach(track=>track.stop());stream.current=null}
  useEffect(()=>{if(!info?.consent)navigate('/');return cleanup},[])
  useEffect(()=>{if(mode==='camera'&&video.current&&stream.current)video.current.srcObject=stream.current},[mode])
  useEffect(()=>()=>{if(url)URL.revokeObjectURL(url);cleanup()},[url])
  const camera=async()=>{setError('');try{stream.current=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});setMode('camera')}catch{setError('Camera access is unavailable. You can choose a photo from your device instead.')}}
  const choose=async(file?:File)=>{if(!file)return;setError('');try{const config=await getPublicConfig();setMaxUploadBytes(config.maxUploadBytes);const size=await validateImage(file,config.maxUploadBytes);setDimensions(size);setPhoto(file);if(url)URL.revokeObjectURL(url);setUrl(URL.createObjectURL(file));cleanup();setMode('preview')}catch(e){setError(e instanceof Error?e.message:'This photo could not be used.')}}
  const take=()=>{if(!video.current)return;const v=video.current,c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d')?.drawImage(v,0,0);c.toBlob(blob=>{if(blob)void choose(new File([blob],'participant-photo.jpg',{type:'image/jpeg'}))},'image/jpeg',.9)}
  const submit=async()=>{if(!photo||busy||!info?.idempotencyKey||!info.consentId||!info.consentVersion||!info.adultConfirmed)return;setBusy(true);setMode('saving');setError('');try{const imageSize=dimensions??await validateImage(photo,maxUploadBytes);const saved=await saveSubmission({photoId:info.idempotencyKey,consentId:info.consentId,consentVersion:info.consentVersion,adultConfirmed:info.adultConfirmed,consentTimestamp:info.consentedAt,image:photo,mimeType:photo.type,fileSize:photo.size,imageWidth:imageSize.width,imageHeight:imageSize.height});setReference(saved.photoId.slice(0,8).toUpperCase());cleanup();setMode('done')}catch(e){setError(e instanceof Error?e.message:'Could not upload the photo. Check your connection and try again.');setMode('preview')}finally{setBusy(false)}}
  const copyReference=async()=>{try{await navigator.clipboard.writeText(reference);setCopied(true);window.setTimeout(()=>setCopied(false),1800)}catch{setError('Could not copy automatically. You can select the reference and copy it manually.')}}
  return <><Header/><main className="flow-page"><Link className="back-link" to="/"><ArrowLeft size={16}/> Back to study information</Link><div className="flow-heading"><span className="eyebrow">YOUR CONTRIBUTION</span><h1>{mode==='done'?'Thank you for taking part.':mode==='preview'?'Check your photo':'Add one photo'}</h1><p>{mode==='done'?'Your photo was uploaded to private study storage.':mode==='preview'?'If it looks clear, submit it securely to the study.':'Take a photo or choose one from your device. You can review it before submitting.'}</p></div>{mode!=='done'&&<div className="steps"><span className="active"><i>1</i> Photo</span><b/><span className={mode==='preview'||mode==='saving'?'active':''}><i>2</i> Review</span><b/><span><i>3</i> Complete</span></div>}
    {mode==='done'?<div className="done-card"><div className="success-icon"><CheckCircle2 size={29}/></div><h2>Photo received</h2><p>Your photo is stored in the study owner’s private Google Drive. You may now close this page.</p><div className="reference"><span>PHOTO REFERENCE</span><b>{reference}</b><button className="button secondary copy-reference" type="button" onClick={()=>void copyReference()} aria-label="Copy photo reference"><Copy size={15}/>{copied?'Copied':'Copy reference'}</button></div><p className="muted">For a withdrawal or deletion request, use the study contact in the consent information.</p><Link className="button secondary" to="/">Return to study</Link></div>:<div className="capture-layout"><section className="capture-card"><div className="capture-stage">{mode==='camera'?<><video ref={video} autoPlay playsInline muted/><div className="face-guide"/><span className="stage-tip">Keep your face centred and look toward the camera.</span></>:mode==='preview'?<><img src={url} alt="Preview of selected participant photo"/><span className="stage-tip">Photo preview</span></>:mode==='saving'?<div className="uploading" role="status" aria-live="polite"><UploadCloud size={36}/><b>Sending photo to the study owner’s private Google Drive…</b><div className="progress" aria-label="Upload in progress"><span/></div><small>Keep this page open until upload completes.</small></div>:<div className="camera-placeholder"><div className="guide-placeholder"><UserRound size={42}/></div><b>Your photo will appear here</b><span>Position your face inside the guide.</span></div>}</div>{mode==='preview'&&photo&&dimensions&&<p className="photo-check" role="status"><CheckCircle2 size={15}/> Basic file checks passed · {dimensions.width} × {dimensions.height}px · {(photo.size/1024/1024).toFixed(1)} MB</p>}{error&&<div className="inline-error" role="alert">{error}</div>}<div className="capture-actions">{mode==='choose'?<><button className="button primary" onClick={()=>void camera()}><Camera size={17}/> Use camera</button><label className="button secondary file-button"><ImagePlus size={17}/> Choose photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value='';void choose(file)}}/></label></>:mode==='camera'?<><button className="button secondary" onClick={()=>{cleanup();setMode('choose')}}>Cancel</button><button className="button primary" onClick={take}><Camera size={17}/> Take photo</button></>:mode==='preview'?<><button className="button secondary" onClick={()=>{setPhoto(null);setDimensions(null);setMode('choose')}}>Choose another</button><button className="button primary" onClick={()=>void submit()} disabled={busy}><UploadCloud size={17}/> Submit photo</button></>:null}</div></section><aside className="guide-card"><h3>For a helpful photo</h3><ul><li><Sun size={16}/> Use soft, natural light</li><li><UserRound size={16}/> Keep your face centred</li><li><span className="guide-dot"/> Choose a plain background</li><li><X size={16}/> Avoid filters and strong shadows</li></ul><p>Where practical, remove anything obscuring facial skin areas. A neutral expression is helpful.</p><div className="privacy-mini"><HardDrive size={15}/> Your photo goes to private study storage after you submit.</div></aside></div>}</main><Footer/></>
}

function Research() {
  const [auth, setAuth] = useState<'checking'|'in'|'out'>('checking')
  useEffect(()=>{void getResearcherSession().then(result=>setAuth(result.authenticated?'in':'out')).catch(()=>setAuth('out'))},[])
  if(auth==='checking') return <><Header/><main className="dashboard"><p className="empty">Checking researcher sign-in…</p></main><Footer/></>
  if(auth==='out') return <ResearchLogin onSignedIn={()=>setAuth('in')}/>
  return <ResearchWorkspace onSignOut={()=>setAuth('out')}/>
}

function ResearchLogin({onSignedIn}:{onSignedIn:()=>void}) {
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{await researcherLogin(username,password);onSignedIn()}catch(err){setError(err instanceof Error?err.message:'Sign-in failed.')}finally{setBusy(false)}}
  return <><Header/><main className="dashboard"><section className="done-card login-card"><div className="modal-icon"><HardDrive size={21}/></div><h2>Researcher sign-in</h2><p>This protected workspace is for authorized study researchers.</p>{error&&<div className="inline-error" role="alert">{error}</div>}<form onSubmit={e=>{e.preventDefault();void submit(e)}} className="login-form"><label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button className="button primary" type="submit" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form></section></main><Footer/></>
}

type ReviewStatus = LocalPhoto['reviewStatus']
type ReviewDraft = { annotation: Annotation; status: ReviewStatus; reason: string }
const annotationFields = CSV_COLUMNS.slice(2) as (keyof Annotation)[]
const reviewSnapshot = (draft: ReviewDraft) => JSON.stringify(draft)

function ResearchWorkspace({onSignOut}:{onSignOut:()=>void}) {
  const [photos,setPhotos]=useState<LocalPhoto[]>([])
  const [selected,setSelected]=useState<LocalPhoto|null>(null)
  const [imageUrl,setImageUrl]=useState('')
  const [imageState,setImageState]=useState<'loading'|'ready'|'error'>('loading')
  const [imageError,setImageError]=useState('')
  const [zoom,setZoom]=useState(1)
  const [filter,setFilter]=useState('all'),[query,setQuery]=useState('')
  const [loading,setLoading]=useState(true),[error,setError]=useState('')
  const [annotation,setAnnotation]=useState<Annotation>(emptyAnnotation())
  const [status,setStatus]=useState<ReviewStatus>('pending'),[reason,setReason]=useState('')
  const [savedSnapshot,setSavedSnapshot]=useState('')
  const [drafts,setDrafts]=useState<Record<string,ReviewDraft>>({})
  const [saving,setSaving]=useState(false),[saveFailed,setSaveFailed]=useState(false)
  const [deleting,setDeleting]=useState(false),[confirmDelete,setConfirmDelete]=useState(false)
  const [notice,setNotice]=useState('')
  const [driveStatus,setDriveStatus]=useState<Awaited<ReturnType<typeof getAdminStatus>>|null>(null)
  const currentSnapshot=reviewSnapshot({annotation,status,reason})
  const dirty=Boolean(selected&&currentSnapshot!==savedSnapshot)

  const refresh=async()=>{setLoading(true);setError('');try{const [items,drive]=await Promise.all([listSubmissions(),getAdminStatus()]);setPhotos(items);setDriveStatus(drive)}catch(e){setError(e instanceof Error?e.message:'Could not load submissions.')}finally{setLoading(false)}}
  useEffect(()=>{void refresh()},[])
  useEffect(()=>()=>{if(imageUrl)URL.revokeObjectURL(imageUrl)},[imageUrl])
  useEffect(()=>{if(!dirty)return;const beforeUnload=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};const guardNavigation=(event:MouseEvent)=>{const anchor=event.target instanceof Element?event.target.closest('a[href]'):null;if(anchor&&!window.confirm('Discard unsaved annotation changes and leave this page?')){event.preventDefault();event.stopPropagation()}};window.addEventListener('beforeunload',beforeUnload);document.addEventListener('click',guardNavigation,true);return()=>{window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('click',guardNavigation,true)}},[dirty])

  const visible=photos.filter(p=>(filter==='all'||p.reviewStatus===filter)&&p.photoId.toLowerCase().includes(query.toLowerCase()))
  const selectedIndex=selected?visible.findIndex(p=>p.photoId===selected.photoId):-1
  const countMissing=(a:Annotation)=>annotationFields.filter(key=>!a[key].trim()).length
  const open=async(photo:LocalPhoto)=>{
    if(dirty&&!window.confirm('Leave this photo with unsaved changes? Your draft will be kept in this session until you return or save it.'))return
    const persisted:ReviewDraft={annotation:{...emptyAnnotation(),...photo.annotation,person_id:photo.participantId,photo_id:photo.photoId},status:photo.reviewStatus,reason:photo.rejectionReason}
    const draft=drafts[photo.photoId]??persisted
    setSelected(photo);setAnnotation(draft.annotation);setStatus(draft.status);setReason(draft.reason);setSavedSnapshot(reviewSnapshot(persisted));setSaveFailed(false);setNotice('');setZoom(1)
    if(imageUrl)URL.revokeObjectURL(imageUrl)
    setImageUrl('');setImageError('');setImageState('loading')
    try{const blob=await getPhotoImage(photo.photoId);setImageUrl(URL.createObjectURL(blob));setImageState('ready')}
    catch(e){setImageError(e instanceof Error?e.message:'Could not load the private photo.');setImageState('error')}
  }
  const closeReview=()=>{if(dirty&&!window.confirm('Close this photo and keep its unsaved draft in this session?'))return;setSelected(null);setImageUrl('')}
  const changeDraft=(next:ReviewDraft)=>{if(!selected)return;const normalized={...next,reason:next.status==='rejected'?next.reason:''};setAnnotation(normalized.annotation);setStatus(normalized.status);setReason(normalized.reason);setDrafts(prev=>({...prev,[selected.photoId]:normalized}));setSaveFailed(false);setNotice('')}
  const save=async()=>{
    if(!selected||saving||!dirty)return
    setSaving(true);setSaveFailed(false);setError('');setNotice('')
    const photoId=selected.photoId
    try{
      await saveReview(photoId,annotation,status,reason)
      const updated:LocalPhoto={...selected,annotation:{...annotation,person_id:selected.participantId,photo_id:selected.photoId},reviewStatus:status,rejectionReason:status==='rejected'?reason:''}
      setSelected(updated);setPhotos(prev=>prev.map(p=>p.photoId===photoId?updated:p))
      setSavedSnapshot(reviewSnapshot({annotation:updated.annotation,status:updated.reviewStatus,reason:updated.rejectionReason}))
      setDrafts(prev=>{const next={...prev};delete next[photoId];return next})
      setNotice('Changes saved.');
    }catch(e){setSaveFailed(true);setError(e instanceof Error?e.message:'Could not save review changes.')}
    finally{setSaving(false)}
  }
  const confirmRemove=async()=>{
    if(!selected||deleting)return
    setDeleting(true);setError('');setNotice('')
    const photoId=selected.photoId
    try{
      await deleteSubmission(photoId)
      setPhotos(prev=>prev.filter(p=>p.photoId!==photoId));setDrafts(prev=>{const next={...prev};delete next[photoId];return next})
      setSelected(null);setImageUrl('');setConfirmDelete(false);setNotice('Photo and associated app record deleted.')
    }catch(e){setError(e instanceof Error?e.message:'Could not delete photo. The record remains available for retry.');setConfirmDelete(false)}
    finally{setDeleting(false)}
  }
  const exportData=()=>void exportReviewedCsv().catch(e=>setError(e instanceof Error?e.message:'CSV export failed.'))
  const linkDrive=async()=>{try{window.location.assign(await connectDrive())}catch(e){setError(e instanceof Error?e.message:'Could not start Google Drive authorization.')}}
  const checkDrive=async()=>{try{await verifyDrive();setNotice('Google Drive connection and private folder verified.');await refresh()}catch(e){setError(e instanceof Error?e.message:'Google Drive verification failed.')}}
  const recover=async()=>{try{const result=await reconcileUploads();setNotice(`Upload recovery checked ${result.checked} record(s) and restored ${result.recovered}.`);await refresh()}catch(e){setError(e instanceof Error?e.message:'Upload recovery failed.')}}
  const signOut=async()=>{if(dirty&&!window.confirm('Discard unsaved annotation changes and sign out?'))return;try{await researcherLogout()}finally{onSignOut()}}
  const statusLabel=(value:ReviewStatus)=>value[0].toUpperCase()+value.slice(1)

  return <><Header/><main className="dashboard" onClickCapture={event=>{const anchor=(event.target as HTMLElement).closest('a');if(dirty&&anchor&&!window.confirm('Discard unsaved annotation changes and leave this page?'))event.preventDefault()}}>
    <div className="dash-top"><div><span className="eyebrow">PROTECTED RESEARCH WORKSPACE</span><h1>Submission review</h1><p>Private photos stored in the study owner’s Google Drive</p></div><div className="dash-actions"><button className="button secondary" onClick={()=>void refresh()} disabled={loading}>{loading?'Refreshing…':'Refresh submissions'}</button><button className="button secondary" onClick={exportData} disabled={!photos.some(p=>p.reviewStatus==='approved')} title={!photos.some(p=>p.reviewStatus==='approved')?'Approve a photo before exporting.':''}><Download size={16}/> Export reviewed dataset</button><button className="button secondary" onClick={()=>void recover()}>Recover uploads</button><button className="button secondary" onClick={()=>void signOut()}>Sign out</button></div></div>
    <div className="local-warning"><HardDrive size={16}/> Google Drive: {driveStatus?.drive_connected?'connected':'not connected'} · {driveStatus?.oauth_configured?'OAuth configured':'OAuth credentials not configured'} {driveStatus?.drive_connected?<button className="text-button" onClick={()=>void checkDrive()}>Verify private folder</button>:<button className="text-button" onClick={()=>void linkDrive()}>Connect Google Drive</button>}</div>
    <div className="metric-row"><div className="metric"><span>Total submissions</span><b>{photos.length}</b></div><div className="metric"><span>Pending photographs</span><b>{photos.filter(p=>p.reviewStatus==='pending').length}</b></div><div className="metric"><span>Reviewed photographs</span><b>{photos.filter(p=>p.reviewStatus==='approved'||p.reviewStatus==='rejected').length}</b></div><div className="metric"><span>Annotations completed</span><b>{photos.filter(p=>annotationFields.every(k=>p.annotation[k]?.trim())).length}</b></div></div>
    {error&&<div className="inline-error" role="alert">{error}</div>}{notice&&<div className="notice-success" role="status"><CheckCircle2 size={16}/>{notice}</div>}
    <div className="review-layout"><section className="queue"><div className="queue-head"><h2>Photographs</h2><input aria-label="Search by photo ID" placeholder="Search photo ID" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Filter review status" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All statuses</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></div>{loading?<p className="empty" role="status">Loading submissions…</p>:visible.length===0?<p className="empty">{photos.length?'No submissions match this search or filter.':'No submissions yet.'}</p>:<div className="photo-list">{visible.map(p=><button key={p.photoId} className={`photo-row ${selected?.photoId===p.photoId?'selected':''}`} aria-current={selected?.photoId===p.photoId?'true':undefined} onClick={()=>void open(p)}><span className="thumb"><ImagePlus size={17}/></span><span className="photo-info"><b>{p.photoId}</b><small>{new Date(p.createdAt).toLocaleString()} · {countMissing(p.annotation)} fields blank</small></span><span className={`status ${p.reviewStatus}`}>{statusLabel(p.reviewStatus)}</span><ChevronRight size={16}/></button>)}</div>}</section>
    {selected?<section className="review-panel" aria-label="Selected photo review"><div className="panel-heading"><div><span className="eyebrow">PHOTO REVIEW</span><h2>{selected.photoId}</h2><span className={`status ${selected.reviewStatus}`}>Saved status: {statusLabel(selected.reviewStatus)}</span></div><button className="icon-button" aria-label="Close photo review" onClick={closeReview}><X size={18}/></button></div>
      <div className="photo-navigation"><button className="button secondary" disabled={selectedIndex<=0} onClick={()=>void open(visible[selectedIndex-1])}><ArrowLeft size={14}/> Previous</button><span>{selectedIndex>=0?`${selectedIndex+1} of ${visible.length}`:'Outside current filters'}</span><button className="button secondary" disabled={selectedIndex<0||selectedIndex>=visible.length-1} onClick={()=>void open(visible[selectedIndex+1])}>Next <ArrowRight size={14}/></button></div>
      <div className="viewer-toolbar"><span>Photo view</span><div role="group" aria-label="Photo zoom controls"><button className="button secondary" onClick={()=>setZoom(1)} aria-pressed={zoom===1}>Fit</button><button className="button secondary" onClick={()=>setZoom(1.5)} aria-pressed={zoom===1.5}>1.5×</button><button className="button secondary" onClick={()=>setZoom(2)} aria-pressed={zoom===2}>2×</button></div></div>
      <div className="review-image" aria-live="polite">{imageState==='loading'?<span role="status">Loading private photo…</span>:imageState==='error'?<div className="image-error" role="alert">{imageError}</div>:imageUrl?<img src={imageUrl} alt="Private participant photo" style={{width:zoom===1?'100%':`${zoom*100}%`,height:'auto',maxHeight:zoom===1?'100%':'none'}}/>:<span>Photo unavailable.</span>}</div>
      <div className="metadata"><span>{selected.imageWidth} × {selected.imageHeight}px</span><span>{(selected.fileSize/1024/1024).toFixed(2)} MB</span><span>{selected.mimeType}</span></div><div className="quality-note">Image checks: {selected.qualityNotes.join(' · ')}</div>
      <div className="annotation-form"><h3>Manual annotation</h3><p>Use only the study’s documented categories. Blank means not recorded; choose “Unknown / not provided” only when that was the annotation.</p><div className="annotation-summary">{countMissing(annotation)} of {annotationFields.length} annotation fields are blank. Partial work can be saved.</div><div className="form-grid">{annotationFields.map(key=><label key={key}>{key.replace(/_/g,' ')}<div className="annotation-input"><input aria-label={key.replace(/_/g,' ')} value={annotation[key]} onChange={e=>changeDraft({annotation:{...annotation,[key]:e.target.value},status,reason})} placeholder="Leave blank if not recorded"/><button className="button secondary mark-unknown" type="button" onClick={()=>changeDraft({annotation:{...annotation,[key]:'Unknown / not provided'},status,reason})}>Mark unknown</button></div></label>)}</div>
        <label className="status-field">Status to save<select value={status} onChange={e=>changeDraft({annotation,status:e.target.value as ReviewStatus,reason})}><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label>{status==='rejected'&&<label className="status-field">Rejection reason<textarea value={reason} onChange={e=>changeDraft({annotation,status,reason:e.target.value})} rows={2}/></label>}
        <div className={`save-state ${saveFailed?'failed':saving?'saving':dirty?'dirty':'saved'}`} role="status">{saving?'Saving…':saveFailed?'Save failed':dirty?'Unsaved changes':'Saved'} · {countMissing(annotation)} fields blank</div><div className="panel-actions"><button className="button secondary danger" onClick={()=>setConfirmDelete(true)}>Delete photo</button><button className="button primary" disabled={saving||!dirty} onClick={()=>void save()}>{saving?'Saving…':'Save changes'} <Check size={16}/></button></div>
      </div></section>:<section className="review-placeholder"><div className="modal-icon"><HardDrive size={21}/></div><h2>Select a private photo</h2><p>Choose a photo to review and annotate. Only a successful save changes its stored review status.</p></section>}</div>
    {!photos.some(p=>p.reviewStatus==='approved')&&<p className="export-note">Export is available after at least one photo is saved with Approved status. Primary export: labels1.csv · fixed column order, no internal IDs or Drive links.</p>}
  </main><Footer/>{confirmDelete&&<div className="overlay" role="presentation"><section className="modal delete-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description"><div className="modal-icon"><X size={21}/></div><h2 id="delete-title">Permanently delete this photo?</h2><p id="delete-description">This removes the photo from Google Drive and deletes its app record, annotations, and consent record. Copies in CSV exports are not affected. {dirty?'Unsaved annotation changes will also be discarded.':''}</p><div className="modal-actions"><button className="button secondary" onClick={()=>setConfirmDelete(false)} disabled={deleting}>Cancel</button><button className="button primary danger-fill" onClick={()=>void confirmRemove()} disabled={deleting}>{deleting?'Deleting…':'Delete permanently'}</button></div></section></div>}</>
}
export default function App() {
  return <Routes><Route path="/" element={<Home/>}/><Route path="/capture" element={<Capture/>}/><Route path="/researcher" element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Research/>}/><Route path="*" element={<main className="not-found"><h1>Page not found</h1><Link to="/">Return home</Link></main>}/></Routes>
}
