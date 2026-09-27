"""Minimal desktop shell. Only this entry point is launched by the user."""
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from devices import validate_settings, PROFILES
from identity import APP_NAME, VERSION
from security import data_root, register_host, private_directory, SingleInstance
from service import Service

def resources():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))

class Window:
    def __init__(self,root,service,assets):
        self.root,self.service,self.assets=root,service,assets
        self.details_window=None;self.closing=False
        root.title(APP_NAME);root.resizable(False,False)
        root.iconbitmap(str(assets/'MSXLiveBridge.ico'))
        root.option_add('*Font',('Yu Gothic UI',10))
        style=ttk.Style(root);style.theme_use('vista')
        outer=ttk.Frame(root,padding=(22,17,20,10));outer.grid(sticky='nsew')
        ttk.Label(outer,text='FTDI',width=6).grid(row=0,column=0,sticky='w',pady=(0,14))
        self.profile=tk.StringVar(value=service.settings['profile'])
        selector=ttk.Combobox(outer,textvariable=self.profile,values=['自動','FT232H','FT232R','Custom'],state='readonly',width=18)
        selector.grid(row=0,column=1,sticky='w',pady=(0,14));selector.bind('<<ComboboxSelected>>',self.change_profile)
        ttk.Label(outer,text='状態',width=6).grid(row=1,column=0,sticky='w')
        status=ttk.Frame(outer);status.grid(row=1,column=1,sticky='w')
        self.dot=tk.Label(status,text='●',fg='#718096',font=('Yu Gothic UI',10));self.dot.pack(side='left',padx=(0,5))
        self.status=tk.StringVar(value='VSIF検索中');ttk.Label(status,textvariable=self.status,width=22).pack(side='left')
        gear=ttk.Button(outer,text='⚙',width=3,command=self.open_details,takefocus=True)
        gear.grid(row=2,column=1,sticky='e',pady=(15,0))
        root.bind('<Control-comma>',lambda _:self.open_details())
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()

    def change_profile(self,*_):
        value=dict(self.service.settings,profile=self.profile.get())
        self.service.configure(value)
        if self.details_window:self.details_window.destroy();self.details_window=None
        if self.profile.get()=='Custom':self.open_details()

    def refresh(self):
        if not self.root.winfo_exists():return
        state=self.service.state();self.status.set(state)
        self.dot.config(fg='#25815b' if state in ('再生中','msxplay待機中') else '#bd7718' if state=='一時停止中' else '#b33a38' if state in ('エラー','VSIFが見つかりません','FTDIは使用中です','FTDI検出エラー') else '#718096')
        if not self.closing:self.root.after(200,self.refresh)

    def open_details(self):
        if self.closing:return
        if self.details_window and self.details_window.winfo_exists():self.details_window.lift();return
        top=tk.Toplevel(self.root);self.details_window=top
        top.title(APP_NAME+' — 詳細設定');top.resizable(False,False);top.transient(self.root)
        top.iconbitmap(str(self.assets/'MSXLiveBridge.ico'))
        body=ttk.Frame(top,padding=20);body.grid(sticky='nsew')
        profile=self.service.settings['profile']
        ttk.Label(body,text='FTDI / VSIF',font=('Yu Gothic UI',11,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        values=['自動選択']+[f'{d.label} — {d.model}' for d in self.service.devices]
        serials=['']+[d.identifier for d in self.service.devices]
        selected=self.service.settings['serial']
        if selected and selected not in serials:serials.append(selected);values.append(selected+' — 未接続')
        device=ttk.Combobox(body,values=values,state='readonly',width=31)
        device.current(serials.index(selected) if selected in serials else 0)
        ttk.Label(body,text='デバイス').grid(row=1,column=0,sticky='w');device.grid(row=1,column=1,pady=4)
        actual=profile
        try:
            d,actual,baud,width,verified=self.service.selection()
            detected=f'検出: {d.model} / {d.label}'
        except LookupError as e:
            baud,width=self.service.settings['baud'],self.service.settings['width'];detected=str(e)
        if profile in PROFILES:baud,width,_=PROFILES[profile]
        if profile=='Custom':baud,width=self.service.settings['baud'],self.service.settings['width']
        ttk.Label(body,text=detected,wraplength=340).grid(row=2,column=0,columnspan=2,sticky='w',pady=(4,12))
        baudvar=tk.StringVar(value=str(baud));widthvar=tk.StringVar(value=str(width))
        for row,label,var in [(3,'baud rate',baudvar),(4,'clock幅',widthvar)]:
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='w')
            ttk.Entry(body,textvariable=var,state='normal' if profile=='Custom' else 'readonly',width=33).grid(row=row,column=1,pady=4)
        note='Custom: 指定した値で送信します。' if profile=='Custom' else 'FT232R: 240,000 baud / 幅25。実機未検証です。' if actual=='FT232R' else 'FT232H: 240,000 baud / 幅32。実機確認済みです。' if actual=='FT232H' else 'プロファイルは接続機器から自動選択します。'
        ttk.Label(body,text=note,wraplength=350).grid(row=5,column=0,columnspan=2,sticky='w',pady=(8,14))
        ttk.Label(body,text='設定を変更すると実機の再生を停止します。',foreground='#666666').grid(row=6,column=0,columnspan=2,sticky='w',pady=(0,14))
        def save():
            try:
                config=dict(self.service.settings,serial=serials[device.current()])
                if profile=='Custom':config.update(baud=int(baudvar.get()),width=int(widthvar.get()))
                self.service.configure(validate_settings(config));top.destroy();self.details_window=None
            except ValueError as e:messagebox.showerror(APP_NAME,str(e),parent=top)
        buttons=ttk.Frame(body);buttons.grid(row=7,column=0,columnspan=2,sticky='ew')
        ttk.Button(buttons,text='診断ログ',command=self.open_logs).pack(side='left')
        ttk.Button(buttons,text='保存',command=save).pack(side='right')

    def open_logs(self):
        top=tk.Toplevel(self.root);top.title(APP_NAME+' — 診断ログ');top.geometry('700x430')
        top.iconbitmap(str(self.assets/'MSXLiveBridge.ico'))
        frame=ttk.Frame(top,padding=12);frame.pack(fill='both',expand=True)
        text=tk.Text(frame,wrap='word',font=('Yu Gothic UI',9));text.pack(fill='both',expand=True)
        def read():
            snapshot=self.service.engine.status()
            try:log=(self.service.root/'diagnostics.log').read_text(encoding='utf-8')[-24000:]
            except OSError:log=''
            details='MSX LiveBridge '+VERSION+'\n'+self.service.device_error+'\n'
            try:
                d,profile,baud,width,verified=self.service.selection()
                details+=f'{d.model} / {d.label}\n{profile}: {baud} baud / clock {width}\n'+('実機確認済み' if verified else '実機未検証')+'\n'
            except LookupError as e:details+=str(e)+'\n'
            text.config(state='normal');text.delete('1.0','end');text.insert('end',details+'\n'+json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n\n'+log);text.config(state='disabled')
        ttk.Button(frame,text='更新',command=read).pack(anchor='e',pady=(10,0));read()

    def close(self):
        if self.closing:return
        self.closing=True;self.status.set('終了中')
        threading.Thread(target=self.service.close,daemon=True).start()
        def finish():
            if self.service.closed:self.root.destroy()
            else:self.root.after(100,finish)
        finish()

def main():
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except OSError:pass
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MSXLiveBridge.Desktop')
    root=tk.Tk();root.withdraw();instance=SingleInstance();service=None
    try:
        if instance.already_running:
            messagebox.showinfo(APP_NAME,'MSX LiveBridgeは既に起動しています。',parent=root);return
        base=resources();data=data_root();private_directory(data)
        register_host(data,base/'native/MSXLiveBridge.Connect.exe')
        service=Service(data,base/'vendor/kss2vgm.exe',base/'native/MSXLiveBridge.Engine.exe')
        Window(root,service,base/'assets');root.deiconify();root.mainloop()
    except Exception as e:messagebox.showerror(APP_NAME,'起動できませんでした。\n'+str(e),parent=root)
    finally:
        if service and not service.closed:service.close()
        instance.close()
        try:root.destroy()
        except tk.TclError:pass

if __name__=='__main__':main()
