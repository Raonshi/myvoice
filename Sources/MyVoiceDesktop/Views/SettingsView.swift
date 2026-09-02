import SwiftUI

struct SettingsView: View {
    @AppStorage("backendExecutable") private var backendExecutable = ""
    @AppStorage("preferredDevice") private var device = "auto"

    var body: some View {
        Form {
            Section("MyVoice 백엔드") {
                TextField("실행 파일", text: $backendExecutable, prompt: Text("자동 검색 (.venv/bin/myvoice)"))
                Text("비워 두면 프로젝트의 .venv, Homebrew 경로, PATH 순서로 찾습니다.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("생성") {
                Picker("기본 처리 장치", selection: $device) {
                    Text("자동 (MPS 우선)").tag("auto")
                    Text("MPS").tag("mps")
                    Text("CPU").tag("cpu")
                }
            }
        }.formStyle(.grouped).padding().frame(width: 520, height: 260)
    }
}
