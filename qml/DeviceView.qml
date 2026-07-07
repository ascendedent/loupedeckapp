import QtQuick
import QtQuick.Layouts

// CT-accurate device mock that MIRRORS the loaded profile: touch-key / side /
// wheel images come from backend.keyImages, and encoders / dial / workspace /
// CT buttons light up when backend.boundActions binds them. Editing (assigning
// actions from the UI) is the next slice.
Item {
    id: dv
    property var theme
    property int cols: backend.columns
    property int rows: backend.rows

    readonly property int keySize: 74
    readonly property int gap: 8

    implicitWidth: body.width
    implicitHeight: body.height

    // ---- profile lookups (recompute on backend.stateChanged) -------------
    function img(key) { return backend.keyImages[key] || "" }
    function bound(key) { return backend.boundActions[key] !== undefined }
    function encBound(base) {
        var b = backend.boundActions
        return b[base] !== undefined || b[base + "-l"] !== undefined || b[base + "-r"] !== undefined
    }
    function actionText(key) { return backend.boundActions[key] || "" }

    // reusable pieces ------------------------------------------------------
    component Encoder: Rectangle {
        property bool active: false
        width: 54; height: 54; radius: 27
        color: theme.cell
        border.color: active ? theme.accent : theme.line
        border.width: 3
        Rectangle {  // knob indicator notch
            width: 4; height: 12; radius: 2
            color: active ? theme.accent : theme.muted
            anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 6
        }
    }

    component RoundBtn: Rectangle {
        property string label: ""
        property bool active: false
        property color activeColor: theme.accent
        width: 40; height: 40; radius: 20
        color: active ? Qt.rgba(activeColor.r, activeColor.g, activeColor.b, 0.22) : theme.cell
        border.color: active ? activeColor : theme.line
        border.width: 2
        Text { anchors.centerIn: parent; text: label
            color: active ? theme.text : theme.muted; font.pixelSize: 11 }
    }

    Rectangle {
        id: body
        width: stack.implicitWidth + 48
        height: stack.implicitHeight + 80
        radius: 22
        color: "#101016"
        border.color: theme.line; border.width: 1

        // submenu breadcrumb badge
        Rectangle {
            visible: backend.menuDepth > 0
            anchors.top: parent.top; anchors.left: parent.left
            anchors.margins: 12
            width: bc.width + 20; height: 24; radius: 12
            color: theme.panel2; border.color: theme.accent
            Text { id: bc; anchors.centerIn: parent
                text: "▸ submenu " + backend.menuDepth
                color: theme.accent; font.pixelSize: 11; font.bold: true }
        }

        ColumnLayout {
            id: stack
            anchors.centerIn: parent
            spacing: 26

            // ---- top zone: encoders | strip | grid | strip | encoders ----
            RowLayout {
                id: topZone
                spacing: 14
                ColumnLayout { spacing: 20
                    Encoder { active: dv.encBound("enc1L") }
                    Encoder { active: dv.encBound("enc2L") }
                    Encoder { active: dv.encBound("enc3L") }
                }

                // left side strip (3 cells)
                ColumnLayout {
                    spacing: dv.gap
                    Repeater {
                        model: ["dis1L", "dis2L", "dis3L"]
                        Rectangle {
                            width: 30; height: dv.keySize; radius: 6
                            color: theme.cell; border.color: theme.line
                            clip: true
                            Image {
                                anchors.fill: parent; anchors.margins: 1
                                source: dv.img(modelData); visible: source != ""
                                fillMode: Image.PreserveAspectCrop; asynchronous: true
                            }
                        }
                    }
                }

                // center touch-key grid
                Rectangle {
                    radius: 8; color: "#07070a"
                    Layout.preferredWidth: grid.width + 12
                    Layout.preferredHeight: grid.height + 12
                    GridLayout {
                        id: grid
                        anchors.centerIn: parent
                        columns: dv.cols; rowSpacing: dv.gap; columnSpacing: dv.gap
                        Repeater {
                            model: dv.cols * dv.rows
                            Rectangle {
                                property int r: Math.floor(index / dv.cols) + 1
                                property int c: index % dv.cols + 1
                                property string key: "tb" + r + c
                                property string src: dv.img(key)
                                width: dv.keySize; height: dv.keySize; radius: 8
                                color: theme.cell; clip: true
                                Image {
                                    anchors.fill: parent; anchors.margins: 1
                                    source: parent.src; visible: source != ""
                                    fillMode: Image.PreserveAspectCrop; asynchronous: true
                                }
                                Rectangle {  // outline
                                    anchors.fill: parent; anchors.margins: 1; radius: 7
                                    color: "transparent"
                                    border.color: dv.bound(parent.key) ? theme.accent : theme.line
                                    border.width: 1
                                }
                                Rectangle {  // bound-but-no-image dot
                                    visible: parent.src == "" && dv.bound(parent.key)
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4; color: theme.accent
                                }
                            }
                        }
                    }
                }

                // right side strip
                ColumnLayout {
                    spacing: dv.gap
                    Repeater {
                        model: ["dis1R", "dis2R", "dis3R"]
                        Rectangle {
                            width: 30; height: dv.keySize; radius: 6
                            color: theme.cell; border.color: theme.line
                            clip: true
                            Image {
                                anchors.fill: parent; anchors.margins: 1
                                source: dv.img(modelData); visible: source != ""
                                fillMode: Image.PreserveAspectCrop; asynchronous: true
                            }
                        }
                    }
                }

                ColumnLayout { spacing: 20
                    Encoder { active: dv.encBound("enc1R") }
                    Encoder { active: dv.encBound("enc2R") }
                    Encoder { active: dv.encBound("enc3R") }
                }
            }

            // ---- workspace round buttons (circle + 1..7) ----
            RowLayout {
                id: wsRow
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                // Labels match the physical CT (1..8). Internally the first
                // button is the firmware 'circle' key, then '1'..'7'; only the
                // displayed number is shifted so the UI reads like the hardware.
                RoundBtn {
                    label: "1"; activeColor: theme.ok
                    active: backend.selectedWs === "circle"
                }
                Repeater {
                    model: 7
                    RoundBtn {
                        label: (index + 2).toString()
                        activeColor: theme.ok
                        active: backend.selectedWs === (index + 1).toString()
                    }
                }
            }

            // ---- CT function buttons + big wheel ----
            RowLayout {
                id: wheelZone
                Layout.alignment: Qt.AlignHCenter
                visible: backend.hasWheel   // CT-only: function buttons + wheel
                spacing: 28

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model: [
                            {l: "⌂", k: "home"}, {l: "↺", k: "undo"},
                            {l: "⌨", k: "keyboard"}, {l: "↵", k: "enter"},
                            {l: "fn", k: "fnL"}, {l: "▤", k: "save"}
                        ]
                        RoundBtn { label: modelData.l; active: dv.bound(modelData.k) }
                    }
                }

                // the big round wheel + dial screen
                Rectangle {
                    width: 180; height: 180; radius: 90
                    color: theme.cell
                    border.color: (dv.bound("dial") || dv.bound("dial-l") || dv.bound("dial-r") || dv.bound("wheel"))
                                  ? theme.accent : theme.line
                    border.width: 3
                    visible: backend.hasWheel
                    Rectangle {  // round screen
                        anchors.centerIn: parent; width: 150; height: 150; radius: 75
                        color: "#07070a"; border.color: theme.line; border.width: 1
                        // wheel image (inscribed square inside the round screen)
                        Image {
                            anchors.centerIn: parent; width: 106; height: 106
                            source: dv.img("wheel"); visible: source != ""
                            fillMode: Image.PreserveAspectCrop; asynchronous: true
                        }
                        Text {
                            anchors.centerIn: parent; text: "WHEEL"
                            visible: dv.img("wheel") == ""
                            color: theme.muted; font.pixelSize: 12; font.letterSpacing: 2
                        }
                    }
                }

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model: [
                            {l: "A", k: "a"}, {l: "B", k: "b"}, {l: "C", k: "c"},
                            {l: "D", k: "d"}, {l: "E", k: "e"}, {l: "fn", k: "fnR"}
                        ]
                        RoundBtn { label: modelData.l; active: dv.bound(modelData.k) }
                    }
                }
            }
        }
    }
}
