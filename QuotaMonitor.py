#!/usr/bin/python
#  QuotaMonitor.py (version 1.4)
#  
#  Copyright 2013 Cody Jackson <cody@jacksontech.net>
#  with contributions from capnchaos64 <martinc@itrans.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

#  Simple quota viewer for the HughesNet HT1000 modem. 
#  Queries the modem at 192.168.0.1 and parses information returned.
#  Depends on wxWidgets-python.
#
#  Does not require any user credentials. Only will work on
#  LANs connected to the HT1000.
#
#  This software is not endorsed by or approved of by HughesNet, nor has
#  it been examined by HughesNet.
#  It was written by a HughesNet customer in hopes that it may
#  be useful to other HughesNet customers.

# Changelog:
# - 15 July 2013: v1.4 Cody Jackson <cody@jacksontech.net>
# * Separated the status message, made it HN9000-only since the HT1000 
#   doesn't expose this information :(
# * Added reset URL for HT1000
#
# - 05 July 2013: v1.3 from martinc@itrans.com
# * object vars for device_info,modem_addr (helpful w/ static IPs)
# * merged GetDeviceInfo,OnShowDeviceInfo,OnResetModem
# * signal quality and terminal status added to status text
#
# - 19 June 2013: v1.2
# * Dynamic icon sizing
# * merged in new regexes from martinc@itrans.com
#
# - 8 June 2013: v1.1b
# * support for HN9000 (including TimeUntilRefil field)
# * added by martinc@itrans.com
#
# - 1 June 2013: v1.0
# * basic display of anytime/bonusbyte quotas in tooltip
# * tiny icon graph


import wx, wx.html, subprocess, urllib, re

# Html window for displaying raw data (or other HTML markup)
class MyHtmlFrame(wx.Frame):
	def __init__(self, parent, title):
		wx.Frame.__init__(self, parent, -1, title)
		self.html = wx.html.HtmlWindow(self)
		if "gtk2" in wx.PlatformInfo:
			self.html.SetStandardFonts()
		self.html.SetPage("<textarea cols=\"80\" rows=\"40\">TESTING</textarea>")
	def SetPage(self,markup):
		self.html.SetPage(markup)

class QuotaMonitor(wx.TaskBarIcon):
	# number of miliseconds between updates
	# you can adjust this (default 15s)
	period = 15000
	
	# icon size (pixels)
	# shouldn't need to adjust in theory
	size = 64
	
	################## don't touch below this line ##################
	# (unless you know what you're doing)

	# modem IP address, can change for static IPs
	modem_addr = "192.168.0.1"
	adapter = ""
	current_sqf = ""
	tx_power = ""
	st_state = ""
	# empty status messages
	current_any = ""
	current_bonus = ""
	status = ""
	# keep device information for general use, updated by "UpdateDevice"
	device_info = ""
	
	# use compiled regex's
	re_adapter = re.compile("^(?:AdapterType=|Adapter=)(\w+)", re.I|re.M)
	re_any = re.compile("^AnyTimeAllowanceRemaining=(\d+)", re.I|re.M)
	re_bonus =  re.compile("^BonusBytesAllowanceRemaining=(\d+)", re.I|re.M)
	re_anytotal = re.compile("^AnyTimePlanAllowance=(\d+)", re.I|re.M)
	re_bonustotal = re.compile("^BonusBytesPlanAllowance=(\d+)", re.I|re.M)
	re_untilrefill = re.compile("^(?:TimeLeftUntilRefill=|FapTimeUntilRefill=)(\d+)", re.I|re.M)
	re_ststate = re.compile("^STState=(\d+)", re.I|re.M)
	re_current_sqf = re.compile("^CurrentSQF=(\d+)", re.I|re.M)
	re_max_sqf = re.compile("^PointingMaxSQF=(\d+)", re.I|re.M)
	re_txpower = re.compile("^UplinkTxPower=(\d+)", re.I|re.M)
	
	version = "1.4"
		
	# create menu
	def CreateMenu(self):
		menu = wx.Menu()
		newItem = menu.Append(wx.ID_ABOUT, "About", "About QuotaMonitor")
		self.Bind(wx.EVT_MENU, self.OnAbout, newItem)
		newItem = menu.Append(wx.ID_PREVIEW, "Show Modem Info", "Show modem device information")
		self.Bind(wx.EVT_MENU, self.OnShowDeviceInfo, newItem)
		newItem = menu.Append(wx.ID_STOP, "Reset Modem", "Reset HughesNet modem")
		self.Bind(wx.EVT_MENU, self.OnResetModem, newItem)
		newItem = menu.Append(wx.ID_EXIT, "Quit", "Close QuotaMonitor")
		self.Bind(wx.EVT_MENU, self.OnQuit, newItem)
		return menu
	
	# event handlers -- right click menu
	def OnTaskBarRight(self, event):
		menu = self.CreateMenu()
		self.PopupMenu(menu)
			
	# quit
	def OnQuit(self, event):
		wx.CallAfter(self.Destroy)
		
	# about
	def OnAbout(self, event):
		wx.MessageBox("QuotaMonitor v" + self.version + "\nCopyright 2013 Cody Jackson <cody@jacksontech.net>\n" \
		+ "With contributions from capnchaos64 <martinc@itrans.com> (HN9000 support!)\n\n" \
		+ "Released under the GPLv2 License.\n" \
		+ "Emails for suggestions or comments welcome", "Info", wx.OK | wx.ICON_INFORMATION)
		
	def OnResetModem(self, event):
		url = "http://" + self.modem_addr
		# default to most recent model modem (HT1000)
		reset_cmd = "/cgi-bin/command.cgi?Command=998" # Seriously, HughesNet?
		if self.adapter == "HN9000":
			# HN9000 software reset, for hardware reset: Crb=Chr
			reset_cmd = "/stlui/fs/advanced/advcfgReboot_req.html?Crb=Csr"
		url += reset_cmd
		try:
			response= urllib.urlopen(url)
		except:
			self.status = "Error sending reset command:\n"+reset_cmd
			self.ErrorIcon()
		
	# on timer fire				
	def OnTimer(self, event):
		self.UpdateQuota() # do the icon/tooltip update

	# show device information
	def OnShowDeviceInfo(self,event):
		frm = MyHtmlFrame(None,self.adapter+' Information')
		markup = '<textarea cols=\"80\" rows=\"40\">'+self.device_info+'</textarea>'
		frm.SetPage(markup)
		frm.Show()
		#wx.MessageBox(markup, "Info", wx.OK | wx.ICON_INFORMATION)
	
	# get device information
	def GetDeviceInfo(self):
		try:
			url = "http://" + self.modem_addr + "/getdeviceinfo/info.bin"
			response = urllib.urlopen(url)
			self.device_info = response.read()
		except IOError:
			# print "Error contacting modem...trying again"
			return False
		return True
			
	# called by timer fire
	# does the update on the icon and tooltip text
	def UpdateQuota(self):
		# get quota data
		if not self.GetDeviceInfo():
			self.status = "Error getting modem information."
			self.ErrorIcon()
			return
		
		# parse
		# thanks to capnchaos64 at dslreports.com forums for suggesting case-insensitive regexes!
		match_adapter = self.re_adapter.search(self.device_info)
		match_any = self.re_any.search(self.device_info)
		match_bonus =  self.re_bonus.search(self.device_info)
		match_anytotal = self.re_anytotal.search(self.device_info)
		match_bonustotal = self.re_bonustotal.search(self.device_info)
		match_untilrefill = self.re_untilrefill.search(self.device_info)
		match_ststate = self.re_ststate.search(self.device_info)
		match_sqf = self.re_current_sqf.search(self.device_info)
		match_max_sqf = self.re_max_sqf.search(self.device_info)
		match_txpower = self.re_txpower.search(self.device_info)
		
		# any fields empty (except optional fields like match_untilrefil)
		if match_any == None or match_bonus == None or match_anytotal == None or match_bonustotal == None or match_adapter == None:
			self.status = "Error parsing modem data...trying again."
			self.ErrorIcon()
		else:
			# generate status tooltip
			
			self.current_any = match_any.group(1)
			self.current_bonus = match_bonus.group(1)
			self.max_any_mb = match_anytotal.group(1)
			self.max_bonus_mb = match_bonustotal.group(1)
			self.adapter = match_adapter.group(1)
			
			
			# HT1000 has time until refil
			if match_untilrefill != None:
				self.until_refill = match_untilrefill.group(1)
				
			# HN9000 has other goodies
			if match_ststate != None:
				self.st_state = match_ststate.group(1)
			if match_sqf != None:
				self.current_sqf = match_sqf.group(1)			
			if match_max_sqf != None:
				self.max_sqf = match_max_sqf.group(1)		
			if match_txpower != None:
				self.tx_power = match_txpower.group(1)
			
			self.status = ""
			
			# add extra status info for the HN9000
			if self.adapter == "HN9000":	
				self.status = "Current SQF: " + self.current_sqf + " (" + str(int(100*float(self.current_sqf)/float(self.max_sqf))) + "%) " \
				+ "\nTx Power: " + self.tx_power + "\nStatus: " + self.st_state + "\n\n"
			
			self.status += "AnyTime quota:\n" + self.current_any + "MB/" + self.max_any_mb + "MB"
			
			# for some reason, 0 == unlimited
			if self.max_bonus_mb == "0": 
				self.status += "\n\nBonus quota:\nUnlimited"
			else:
				self.status += "\n\nBonus quota:\n" + self.current_bonus + "MB/" + self.max_bonus_mb + "MB"
				
			if self.adapter == "HT1000":	
				# HT1000 report time until refil
				self.status += "\n\n" + str(int(self.until_refill)/60/24) + " days until refill"
			elif self.adapter == "HN9000":
				self.status += "\n\n" + str(int(self.until_refill)/60) + " hours until refill"
			
			# generate new icon
			self.UpdateIcon()
		
	# generates an icon with red X
	def ErrorIcon(self):
		# start with empty icon
		icon_bitmap = wx.EmptyBitmapRGBA(self.size, self.size, 64, 64, 64, 255)
		dc = wx.MemoryDC()
		dc.SelectObject(icon_bitmap)
		dc.SetPen(wx.RED_PEN)
		
		# draw scary red Xs
		dc.DrawLine(0, 0, self.size-1, self.size-1)
		dc.DrawLine(self.size-1, 0, 0, self.size-1)
		dc.SelectObject(wx.NullBitmap)
		
		# set up icon
		icon = wx.EmptyIcon()
		icon.CopyFromBitmap(icon_bitmap)
		self.SetIcon(icon, self.status)
	
	# generates icon with graph
	def UpdateIcon(self):
		# start with empty icon
		icon_bitmap = wx.EmptyBitmapRGBA(self.size, self.size, 64, 64, 64, 255)
		
		# if we have data
		if self.current_any and self.current_bonus:
			# generate ratio (e.g. 4000/1000 = 0.4)
			any_ratio = float(self.current_any)/float(self.max_any_mb)
			if self.max_bonus_mb == "0":
				bonus_ratio = 1
			else:
				bonus_ratio = float(self.current_bonus)/float(self.max_bonus_mb)
		
			# find the height of the bars
			any_height = (self.size * any_ratio)
			bonus_height = (self.size * bonus_ratio)

			# find their offset from the top
			any_top = self.size - any_height
			bonus_top = self.size - bonus_height

			dc = wx.MemoryDC()
			dc.SelectObject(icon_bitmap)

			dc.SetPen(wx.TRANSPARENT_PEN)
			# pick color for anytime
			if any_ratio > 0.5:
				any_colour = wx.Color(0,255,0,255)
			elif any_ratio > 0.2:
				any_colour = wx.Color(224,192,0,255)
			else:
				any_colour = wx.Color(255,0,0,255)

			# pick color for bonus
			if bonus_ratio > 0.5:
				bonus_colour = wx.Color(0,128,255,255)
			elif bonus_ratio > 0.2:
				bonus_colour = wx.Color(224,32,192,255)
			else:
				bonus_colour = wx.Color(255,0,0,255)
			
			# draw anytime graph
			dc.SetBrush(wx.Brush(any_colour))
			dc.DrawRectangle(0,any_top,(self.size/2)-1,any_height)

			# draw bonus graph
			dc.SetBrush(wx.Brush(bonus_colour))
			dc.DrawRectangle(self.size/2,bonus_top,(self.size/2)-1,bonus_height)
	
			# I don't like this much - Supertanker
			# draw gray line down center
			# dc.SetBrush(wx.Brush(wx.Color(160,160,160,255)))
			# dc.DrawRectangle(self.size-1,0,4,self.size)
			
			# done, deselect the bitmap
			dc.SelectObject(wx.NullBitmap)
		
		# generate icon
		icon = wx.EmptyIcon()
		
		# copy data into icon
		icon.CopyFromBitmap(icon_bitmap)
		# set icon
		self.SetIcon(icon, self.status)
		
	# constructor
	def __init__(self): 
		super(QuotaMonitor, self).__init__()
	
		self.UpdateQuota()
		
		# set up timer for refresh
		self.timer = wx.Timer(self)
		self.timer.Start(self.period)

		# event handlers
		wx.EVT_TASKBAR_RIGHT_UP(self, self.OnTaskBarRight)
		
		self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)

# main program loop
def main():
	app = wx.PySimpleApp()
	QuotaMonitor()
	app.MainLoop()

# entry point
if __name__ == '__main__':
    main()
