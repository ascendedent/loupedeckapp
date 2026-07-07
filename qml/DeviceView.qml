import QtQuick
import QtQuick.Layouts

// CT-accurate device mock that MIRRORS the loaded profile and lets you SELECT a
// control (tap it) to edit in the right-hand inspector. Images come from
// backend.keyImages; bound controls light up from backend.boundActions; the
// selected control gets an 'ok'-coloured ring.
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
    function isSel(key) { return key !== "" && backend.selectedControl === key }

    // reusable pieces ------------------------------------------------------
    component Encoder: Rectangle {
        property bool active: false
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 54; height: 54; radius: 27
        color: sel ? Qt.rgba(theme.ok.r, theme.ok.g, theme.ok.b, 0.18) : theme.cell
        border.color: sel ? theme.ok : (active ? theme.accent : theme.line)
        border.width: 3
        Rectangle {  // knob indicator notch
            width: 4; height: 12; radius: 2
            color: (active || sel) ? theme.text : theme.muted
            anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 6
        }
        TapHandler { enabled: ctlKey !== ""; onTapped: backend.selectControl(ctlKey) }
    }

    component RoundBtn: Rectangle {
        property string label: ""
        property bool active: false
        property color activeColor: theme.accent
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 40; height: 40; radius: 20
        color: sel ? Qt.rgba(theme.ok.r, theme.ok.g, theme.ok.b, 0.22)
             : (active ? Qt.rgba(activeColor.r, activeColor.g, activeColor.b, 0.22) : theme.cell)
        border.color: sel ? theme.ok : (active ? activeColor : theme.line)
        border.width: 2
        Text { anchors.centerIn: parent; text: label
            color: (active || sel) ? theme.text : theme.muted; font.pixelSize: 11 }
        TapHandler { enabled: ctlKey !== ""; onTapped: backend.selectControl(ctlKey) }
    }

    component SideCell: Rectangle {
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 30; height: dv.keySize; radius: 6
        color: theme.cell
        border.color: sel ? theme.ok : (dv.bound(ctlKey) ? theme.accent : theme.line)
        border.width: sel ? 2 : 1
        clip: true
        Image {
            anchors.fill: parent; anchors.margins: 1
            source: dv.img(ctlKey); visible: source != ""
            fillMode: Image.PreserveAspectCrop; asynchronous: true
        }
        TapHandler { onTapped: backend.selectControl(ctlKey) }
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
                    Encoder { ctlKey: "enc1L"; active: dv.encBound("enc1L") }
                    Encoder { ctlKey: "enc2L"; active: dv.encBound("enc2L") }
                    Encoder { ctlKey: "enc3L"; active: dv.encBound("enc3L") }
                }

                // left side strip (3 cells)
                ColumnLayout {
                    spacing: dv.gap
                    Repeater {
                        model: ["dis1L", "dis2L", "dis3L"]
                        SideCell { ctlKey: modelData }
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
                                property bool sel: dv.isSel(key)
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
                                    border.color: parent.sel ? theme.ok
                                                : (dv.bound(parent.key) ? theme.accent : theme.line)
                                    border.width: parent.sel ? 2 : 1
                                }
                                Rectangle {  // bound-but-no-image dot
                                    visible: parent.src == "" && dv.bound(parent.key)
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4; color: theme.accent
                                }
                                TapHandler { onTapped: backend.selectControl(parent.key) }
                            }
                        }
                    }
                }

                // right side strip
                ColumnLayout {
                    spacing: dv.gap
                    Repeater {
                        model: ["dis1R", "dis2R", "dis3R"]
                        SideCell { ctlKey: modelData }
                    }
                }

                ColumnLayout { spacing: 20
                    Encoder { ctlKey: "enc1R"; active: dv.encBound("enc1R") }
                    Encoder { ctlKey: "enc2R"; active: dv.encBound("enc2R") }
                    Encoder { ctlKey: "enc3R"; active: dv.encBound("enc3R") }
                }
            }

            // ---- workspace round buttons (labelled 1..8 like the hardware) ----
            RowLayout {
                id: wsRow
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                // First button is the firmware 'circle' key; only the label is
                // shifted so the UI reads 1..8 like the physical CT.
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
                        RoundBtn { label: modelData.l; ctlKey: modelData.k; active: dv.bound(modelData.k) }
                    }
                }

                // the big round wheel + dial screen (outer ring = dial, inner = wheel)
                Rectangle {
                    width: 180; height: 180; radius: 90
                    color: theme.cell
                    border.color: dv.isSel("dial") ? theme.ok
                                : ((dv.bound("dial") || dv.bound("dial-l") || dv.bound("dial-r")) ? theme.accent : theme.line)
                    border.width: 3
                    TapHandler { onTapped: backend.selectControl("dial") }   // ring
                    Rectangle {  // round screen (wheel)
                        anchors.centerIn: parent; width: 150; height: 150; radius: 75
                        color: "#07070a"
                        border.color: dv.isSel("wheel") ? theme.ok
                                    : (dv.bound("wheel") ? theme.accent : theme.line)
                        border.width: dv.isSel("wheel") ? 2 : 1
                        TapHandler { onTapped: backend.selectControl("wheel") }
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
                        RoundBtn { label: modelData.l; ctlKey: modelData.k; active: dv.bound(modelData.k) }
                    }
                }
            }
        }
    }
}
