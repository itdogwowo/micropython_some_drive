#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SD 卡管理工具 (Mac / Windows)

用法: python3 storage_tool.py
"""

import subprocess as SP, os, sys, json, re, time, hashlib, platform, shutil
S=512; OS=platform.system()

def I(msg,defv=""):
    """input: enter=預設, q=取消"""
    r=input(msg).strip()
    if r.lower() in ("q","cancel"): return None
    return r if r else defv

def R(c): return SP.run(c,capture_output=True,text=True)
def RS(c): return SP.run(c,capture_output=True,text=True,shell=True)

# ── 平台層 ──
def _scan():
    d=[]
    if OS=="Darwin":
        r=R(["diskutil","list","external","physical"])
        for dev in re.findall(r"^(/dev/disk\d+)",r.stdout,re.M):
            i=R(["diskutil","info",dev]).stdout
            m=re.search(r"\((\d+)\s*Bytes?\)",i)
            if m and int(m.group(1))>=512*1024*1024: d.append((dev,int(m.group(1))))
    elif OS=="Windows":
        r=RS("wmic diskdrive get size,index /format:csv")
        for line in r.stdout.strip().split("\n")[1:]:
            p=line.split(",")
            if len(p)>=2:
                try: sz=int(p[0])
                except: continue
                if sz>=512*1024*1024: d.append(("PhysicalDrive"+p[1].strip(),sz))
    return d

def _mp(dev):
    if OS=="Darwin":
        for p in ["/Volumes/SDCARD","/Volumes/NO NAME"]:
            if os.path.exists(p): return p
        R(["diskutil","mountDisk",dev]);R(["diskutil","mount",dev+"s1"]);time.sleep(1)
        if os.path.exists("/Volumes/SDCARD"): return "/Volumes/SDCARD"
    elif OS=="Windows":
        for l in "DEFGHIJKLMNOPQRSTUVWXYZ":
            if os.path.exists(l+":/alloc.json"): return l+":"
    return None

def _unmount(dev):
    if OS=="Darwin": R(["diskutil","unmountDisk",dev])

def _fmt(dev):
    if OS=="Darwin":
        R(["diskutil","unmountDisk",dev])
        return R(["diskutil","eraseDisk","FAT32","SDCARD",dev]).returncode==0
    return False

def _w(dev,data,off):
    sz=((len(data)+S-1)//S)*S
    if OS=="Darwin":
        import shutil; pv=shutil.which("pv")
        tmp="/tmp/_ul.bin"
        open(tmp,"wb").write(data.ljust(sz,b"\x00"))
        if pv: RS("sudo dd if="+tmp+" bs=512 2>/dev/null | "+pv+" -s "+str(sz)+" 2>/dev/null | sudo dd of="+dev+" bs=512 seek="+str(off)+" 2>/dev/null")
        else: RS("sudo dd if="+tmp+" of="+dev+" bs=512 seek="+str(off)+" 2>/dev/null")
    elif OS=="Windows":
        with open("\\\\.\\"+dev,"wb") as f: f.seek(off*S); f.write(data.ljust(sz,b"\x00"))

def _r(dev,off,cnt,out):
    sz=cnt*S
    if OS=="Darwin":
        pv=shutil.which("pv")
        if pv: RS("sudo dd if="+dev+" bs=512 skip="+str(off)+" count="+str(cnt)+" 2>/dev/null | "+pv+" -s "+str(sz)+" > "+out)
        else: RS("sudo dd if="+dev+" of="+out+" bs=512 skip="+str(off)+" count="+str(cnt)+" 2>/dev/null")
    elif OS=="Windows":
        with open("\\\\.\\"+dev,"rb") as f: f.seek(off*S); d=f.read(sz)
        open(out,"wb").write(d)

# ── 功能 ──
def A(dev):
    m=_mp(dev)
    p=os.path.join(m,"alloc.json") if m else None
    return json.load(open(p)) if p and os.path.exists(p) else None

def F(dev,cap):
    v=I("FAT MB [32]: ","32")
    if v is None: return
    f=int(v)
    if f<=0: _fmt(dev); print("✅"); return
    off=f*1048576//512; t=cap//512
    print("sector:{} FAT:{}MB managed:~{:.1f}GB".format(off,off*512/1048576,(t-off)*512/1073741824))
    if I("確認? (yes): ") is None: return
    if not _fmt(dev): print("❌"); return
    m=_mp(dev)
    a={"_version":1,"_offset":off,"_total_sectors":t}
    if m:
        json.dump(a,open(os.path.join(m,"alloc.json"),"w"),indent=2)
        print("✅ alloc.json (offset={})".format(off))
    _unmount(dev)

def P(dev):
    a=A(dev)
    if not a: print("❌"); return
    off=a.get("_offset","?"); t=a.get("_total_sectors",0)
    print(" Managed Area sector:{}  ({:.1f}MB)".format(off,off*512/1048576))
    if t: print("  總容量: {} sectors ({:.1f}GB)".format(t,t*512/1073741824))
    print("─"*72)
    i=1; u=0
    for k,v in sorted(a.items(),key=lambda x:x[1][0] if isinstance(x[1],list) else 0):
        if k.startswith("_"): continue
        sz="{:.0f}K".format(v[1]*512/1024) if v[1]*512<1048576 else "{:.1f}M".format(v[1]*512/1048576)
        pct="{:>5.1f}".format(v[1]*100/t) if t else "?"
        sh=" "+v[2][:10] if len(v)>=3 and v[2] else ""
        print(" {:>2d}. {:24s} sec{:>8,d} {:>8s} {:>5s}%{:>12s}".format(i,k[:24],v[0],sz,pct,sh[:10]))
        u+=v[1]; i+=1
    print("─"*72)
    print(" 合計: {} 檔案, {} sectors, {:.1f}M, {:.1f}%".format(i-1,u,u*512/1048576,u*100/t if t else 0))

def DL(dev):
    a=A(dev)
    if not a: return
    fs=[k for k in a if not k.startswith("_")]
    if not fs: return
    for i,n in enumerate(fs): print(" {}. {} (sec{})".format(i+1,n,a[n][0]))
    v=I("選擇: "); 
    if v is None: return
    n=int(v)-1; name=fs[n]; sec,cnt=a[name][0],a[name][1]
    out=I("路徑 [./{}]: ".format(name),"./"+name)
    if out is None: return
    if os.path.exists(out):
        if I("⚠️ 覆蓋? (yes/no): ") is None: return
    _unmount(dev); _r(dev,sec,cnt,out)
    d=open(out,"rb").read()
    print("\n✅ {} bytes".format(len(d)))
    if len(a[name])>=3 and a[name][2]:
        h=hashlib.sha256(d).hexdigest()
        print("✅ SHA256 ok" if h==a[name][2] else "⚠️ mismatch")

def UL(dev):
    a=A(dev)
    if not a: return
    p=I("檔案路徑: ")
    if p is None or not os.path.exists(p): return
    fs=os.path.getsize(p); sh=hashlib.sha256(open(p,"rb").read()).hexdigest()
    print("SHA256:",sh[:24],fs)
    dup=None
    for k,v in a.items():
        if k.startswith("_"): continue
        if len(v)>=3 and v[2]==sh: dup=k; break
        if v[1]*S==fs: dup=dup or k
    if dup:
        print("⚠️ 與 {} 重複".format(dup))
        v=I("跳過? (enter=yes, r=rename): ")
        if v is None: return
        if v.lower().startswith("r"):
            v2=I("新名: ")
            if v2 is None: return
            name=v2
        else: return
    else:
        v=I("名 [{}]: ".format(os.path.basename(p)))
        if v is None: return
        name=v or os.path.basename(p)
    if name in a:
        v=I("覆蓋? (enter=yes, r=rename, q=cancel): ").lower()
        if v is None: return
        if v.startswith("r"):
            v2=I("新名: ")
            if v2 is None: return
            name=v2
        elif v not in ("yes","y",""): return
    data=open(p,"rb").read(); cnt=(len(data)+S-1)//S
    tail=a["_offset"]
    for k,v in a.items():
        if k.startswith("_"): continue
        tail=max(tail,v[0]+v[1])
    _unmount(dev); _w(dev,data,tail)
    m=_mp(dev)
    if m:
        r=json.load(open(os.path.join(m,"alloc.json")))
        r[name]=[tail,cnt,sh]
        json.dump(r,open(os.path.join(m,"alloc.json"),"w"),indent=2)
        print("\n✅ {} sector{}~{}".format(name,tail,tail+cnt))

def TR(dev):
    a=A(dev)
    if not a: return
    fs=[k for k in a if not k.startswith("_")]
    if not fs: return
    for i,n in enumerate(fs): print(" {}. {}".format(i+1,n))
    v=I("選擇: ")
    if v is None: return
    n=int(v)-1; name=fs[n]
    if I("確認? (yes): ") is None: return
    s=a[name][0]; m=_mp(dev)
    if m:
        r=json.load(open(os.path.join(m,"alloc.json")))
        rm=[k for k,v in r.items() if not k.startswith("_") and v[0]>=s]
        for k in rm: del r[k]
        json.dump(r,open(os.path.join(m,"alloc.json"),"w"),indent=2)
        print("✅ 刪除:",", ".join(rm))

def main():
    print("\nSD 卡工具 (OS: {})\n{}".format(OS,"="*50))
    disks=_scan()
    if not disks: print("❌ 找不到 SD 卡"); return
    for i,(d,c) in enumerate(disks): print(" {}. {}  ({:.1f}GB)".format(i+1,d,c/1073741824))
    n=I("選擇: ")
    if n is None: return
    dev,cap=disks[int(n)-1]
    while True:
        print("\nDevice:",dev); print("1.格式化 2.列表 3.下載 4.上傳 5.刪除 0.離開")
        c=I("選擇: ")
        if c is None: break
        if c=="1": F(dev,cap)
        elif c=="2": P(dev)
        elif c=="3": DL(dev)
        elif c=="4": UL(dev)
        elif c=="5": TR(dev)
        elif c=="0": break

if __name__=="__main__":
    main()
