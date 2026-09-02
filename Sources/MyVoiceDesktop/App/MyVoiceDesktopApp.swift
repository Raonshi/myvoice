import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
struct MyVoiceDesktopApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(store)
        }
        .defaultSize(width: 1040, height: 700)
        .commands {
            CommandMenu("MyVoice") {
                Button("새로 고침") { Task { await store.refresh() } }.keyboardShortcut("r")
                Divider()
                Button("음성 생성") { store.selection = .generate }.keyboardShortcut("g")
                Button("음성 등록") { store.selection = .enroll }.keyboardShortcut("e")
                Button("발음 사전") { store.selection = .pronunciationDictionaries }
                    .keyboardShortcut("p", modifiers: [.command, .shift])
                Button("시스템 진단") { store.selection = .doctor }.keyboardShortcut("d", modifiers: [.command, .shift])
            }
        }
        Settings { SettingsView() }
    }
}
