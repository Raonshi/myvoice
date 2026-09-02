import SwiftUI

struct DoctorView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading) {
                    Text("시스템 진단").font(.largeTitle.bold())
                    Text("Chatterbox, FFmpeg와 Apple Silicon MPS 실행 환경을 확인합니다.").foregroundStyle(.secondary)
                }
                Spacer()
                Button("진단 실행") { Task { await store.diagnose() } }.buttonStyle(.borderedProminent).disabled(store.isWorking)
            }
            if let doctor = store.doctor {
                Table(doctor.checks) {
                    TableColumn("항목", value: \.name).width(min: 130, ideal: 170)
                    TableColumn("결과") { check in
                        Label(check.status.uppercased(), systemImage: symbol(check.status)).foregroundStyle(color(check.status))
                    }.width(100)
                    TableColumn("상세", value: \.detail)
                }
                Text("자동 선택 장치: \(doctor.autoDevice)").font(.callout.weight(.semibold))
            } else {
                ContentUnavailableView("아직 진단하지 않았습니다", systemImage: "stethoscope", description: Text("진단 실행을 눌러 현재 환경을 확인하세요."))
            }
        }.padding(24).navigationTitle("시스템 진단")
    }

    private func symbol(_ status: String) -> String { status == "ok" ? "checkmark.circle.fill" : status == "fail" ? "xmark.circle.fill" : "exclamationmark.triangle.fill" }
    private func color(_ status: String) -> Color { status == "ok" ? .green : status == "fail" ? .red : .orange }
}
