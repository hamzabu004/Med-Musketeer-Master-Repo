"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/ui/page-intro";
import { services } from "@/services";
import type { Device } from "@/types";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { inputClass, LabeledStatus } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

const workflow=["Register","Verify identity","Activate","Assign patient","Assign Monitoring Station"];

export function AdminDeviceRegistration(){
  const {state,refresh}=useAdminOverview(); const router=useRouter(); const [step,setStep]=useState(0); const [error,setError]=useState("");
  const [form,setForm]=useState({id:"",identity:"",firmwareVersion:"0.8.2",patientId:"",stationId:""});
  if(state.status==="loading")return <AdminPageSkeleton/>;if(state.status==="error")return <AdminPageError message={state.message} onRetry={refresh}/>;
  const data=state.data; const organizationId=data.session.organizationId;
  async function submit(event:React.FormEvent){event.preventDefault();setError("");const id=form.id.trim().toUpperCase();const identity=form.identity.trim();if(!id||!identity||!form.patientId||!form.stationId){setError("Complete every workflow field before registering the wearable.");return;}if(await services.devices.get(organizationId,id)){setError("That device ID is already registered.");return;}
    try{setStep(1);const device:Device={id,organizationId,type:"ecg-wearable",patientId:null,monitoringStationId:null,status:"pending",batteryPercent:100,firmwareVersion:form.firmwareVersion.trim()||"0.8.2",identity,lastSeenAt:"2026-09-10T05:00:00+05:00"};await services.devices.save(organizationId,device);setStep(2);await services.devices.setStatus(organizationId,id,"online");setStep(3);await services.devices.assignPatient(organizationId,id,form.patientId);setStep(4);await services.devices.assignMonitoringStation(organizationId,id,form.stationId);setStep(5);setTimeout(()=>router.push("/admin/devices"),400);}catch(e){setError(e instanceof Error?e.message:"Device registration failed.");}
  }
  return <section className="mx-auto max-w-5xl space-y-5"><PageIntro title="Register Device" description="A five-step simulated onboarding workflow. The resulting wearable is stored only in this browser."/>
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="Registration workflow">{workflow.map((label,index)=><li key={label} className="rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm"><span className="metric-number mr-2 font-semibold">{index+1}</span>{label}<span className="mt-2 block"><LabeledStatus value={step>index?"resolved":step===index&&step>0?"active":"pending"}/></span></li>)}</ol>
    <Card className="p-5"><form className="grid gap-4 sm:grid-cols-2" onSubmit={e=>void submit(e)}><label className="text-sm font-medium">Device ID<input className={inputClass} value={form.id} onChange={e=>setForm({...form,id:e.target.value})} placeholder="DEV-004" required/></label><label className="text-sm font-medium">Identity value<input className={inputClass} value={form.identity} onChange={e=>setForm({...form,identity:e.target.value})} placeholder="mm-dev-004" required/></label><label className="text-sm font-medium">Firmware version<input className={inputClass} value={form.firmwareVersion} onChange={e=>setForm({...form,firmwareVersion:e.target.value})} required/></label><label className="text-sm font-medium">Assign patient<select className={inputClass} value={form.patientId} onChange={e=>setForm({...form,patientId:e.target.value})} required><option value="">Choose patient</option>{data.patients.map(p=><option key={p.id} value={p.id}>{p.displayName} ({p.id})</option>)}</select></label><label className="text-sm font-medium sm:col-span-2">Assign Monitoring Station<select className={inputClass} value={form.stationId} onChange={e=>setForm({...form,stationId:e.target.value})} required><option value="">Choose Monitoring Station</option>{data.stations.map(s=><option key={s.id} value={s.id}>{s.name} ({s.id})</option>)}</select></label>{error&&<p role="alert" className="sm:col-span-2 text-sm text-[var(--color-critical)]">{error}</p>}<div className="sm:col-span-2"><Button type="submit" disabled={step>0}>{step===5?"Registration complete":step>0?"Processing workflow…":"Register and complete workflow"}</Button></div></form></Card>
    <p className="text-xs text-[var(--color-text-muted)]">Identity verification and activation are deterministic simulations; no real wearable is contacted and no production credential is issued.</p>
  </section>;
}
