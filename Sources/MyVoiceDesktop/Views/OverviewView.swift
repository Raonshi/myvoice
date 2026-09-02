import SwiftUI

struct OverviewView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("내 목소리로 자연스러운 내레이션을 만드세요")
                        .font(.largeTitle.bold())
                    Text("음성 데이터와 생성 결과는 이 Mac에만 저장됩니다.")
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 16) {
                    metric("Voice Profiles", value: store.voices.count, symbol: "person.wave.2")
                    metric("생성 작업", value: store.jobs.count, symbol: "waveform")
                    metric("완료", value: store.jobs.filter { $0.status == "completed" }.count, symbol: "checkmark.circle")
                }
                GroupBox("빠른 시작") {
                    HStack(spacing: 12) {
                        action("새 목소리 등록", symbol: "mic.badge.plus", destination: .enroll)
                        action("음성 생성", symbol: "waveform", destination: .generate)
                        action("시스템 확인", symbol: "stethoscope", destination: .doctor)
                    }.padding(8)
                }
                if let recent = store.jobs.first {
                    GroupBox("최근 작업") {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(recent.id).font(.headline)
                                Text("\(recent.voiceName) · \(recent.segments.count)개 세그먼트")
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            StatusBadge(status: recent.status)
                        }.padding(8)
                    }
                }
            }.padding(28)
        }.navigationTitle("개요")
    }

    private func metric(_ title: String, value: Int, symbol: String) -> some View {
        GroupBox {
            HStack {
                Image(systemName: symbol).font(.title2).foregroundStyle(.tint)
                VStack(alignment: .leading) {
                    Text(value.formatted()).font(.title.bold())
                    Text(title).foregroundStyle(.secondary)
                }
                Spacer()
            }.padding(8)
        }.frame(maxWidth: .infinity)
    }

    private func action(_ title: String, symbol: String, destination: SidebarItem) -> some View {
        Button { store.selection = destination } label: {
            Label(title, systemImage: symbol).frame(maxWidth: .infinity).padding(.vertical, 8)
        }.buttonStyle(.bordered)
    }
}

struct StatusBadge: View {
    let status: String
    var body: some View {
        Text(status).font(.caption.weight(.semibold)).padding(.horizontal, 9).padding(.vertical, 4)
            .background(color.opacity(0.14), in: Capsule()).foregroundStyle(color)
    }
    private var color: Color {
        switch status {
        case "completed": .green
        case "failed": .red
        case "generating", "assembling", "encoding", "regenerating": .orange
        default: .secondary
        }
    }
}
