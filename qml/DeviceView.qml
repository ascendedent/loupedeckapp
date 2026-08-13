import QtQuick
import QtQuick.Layouts
import QtQuick.Effects

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
    function label(key) { return backend.controlLabels[key] }
    function led(key) { return backend.controlLeds[key] || "" }
    function bg(key) { return backend.controlBgs[key] || "" }
    // approximate the device's shrink-mode label band height for the mirror
    function shrinkBand(h) { return Math.round(h * 0.3) }

    // text-label overlay for image-bearing controls (mirrors the device:
    // over = text over the image; bar = text on a band; shrink = band at an edge
    // with the image resized beside it; the image inset is done by each cell)
    component CtrlLabel: Item {
        id: cl
        property var lbl: undefined
        anchors.fill: parent
        visible: lbl !== undefined && lbl !== null
        readonly property string lmode: lbl ? (lbl.mode || "over") : "over"
        readonly property string lpos: lbl ? (lbl.pos || "bottom") : "bottom"
        readonly property int pad: 2
        // one text position for every mode so shrink clears the edge like bar does
        readonly property real textY: lpos === "top" ? 6
            : lpos === "middle" ? (height - lt.implicitHeight) / 2
            : height - lt.implicitHeight - 10
        Rectangle {   // band behind the text (bar + shrink modes)
            visible: cl.lmode === "bar" || cl.lmode === "shrink"
            width: parent.width
            color: (cl.lbl && cl.lbl.bar_color) ? cl.lbl.bar_color : Qt.rgba(0, 0, 0, 0.82)
            // bar: wrap the text; shrink: run from the text to the near edge
            y: (cl.lmode === "shrink" && cl.lpos === "top") ? 0 : (cl.textY - cl.pad)
            height: cl.lmode !== "shrink" ? (lt.implicitHeight + 2 * cl.pad)
                  : (cl.lpos === "top" ? (cl.textY + lt.implicitHeight + cl.pad)
                                       : (cl.height - (cl.textY - cl.pad)))
        }
        Text {
            id: lt
            text: cl.lbl ? (cl.lbl.text || "") : ""
            color: "white"; font.pixelSize: 11; font.bold: true
            width: parent.width; horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight; maximumLineCount: 1
            style: Text.Outline; styleColor: "black"
            y: cl.textY
        }
    }

    // reusable pieces ------------------------------------------------------
    component Encoder: Rectangle {
        id: enc
        property bool active: false
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 54; height: 54; radius: 27
        color: sel ? Qt.rgba(theme.ok.r, theme.ok.g, theme.ok.b, 0.18) : theme.cell
        border.color: encDrop.containsDrag ? theme.accent
                    : (sel ? theme.ok : (active ? theme.accent : theme.line))
        border.width: encDrop.containsDrag ? 4 : 3
        Rectangle {  // knob indicator notch (hidden while choosing a drop slot)
            visible: !encDrop.containsDrag
            width: 4; height: 12; radius: 2
            color: (active || sel) ? theme.text : theme.muted
            anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 6
        }
        TapHandler { enabled: ctlKey !== ""; onTapped: backend.selectControl(ctlKey) }
        // one drop target; the vertical third under the cursor picks the slot
        // (top = rotate ◀, middle = press, bottom = rotate ▶)
        DropArea {
            id: encDrop; anchors.fill: parent
            property int zone: 1
            onPositionChanged: (drag) => { var t = height / 3
                zone = drag.y < t ? 0 : (drag.y < 2 * t ? 1 : 2) }
            onDropped: (drop) => {
                if (enc.ctlKey === "" || !drop.source) return
                var t = height / 3
                var z = drop.y < t ? 0 : (drop.y < 2 * t ? 1 : 2)
                var slot = z === 0 ? enc.ctlKey + "-l" : z === 2 ? enc.ctlKey + "-r" : enc.ctlKey
                backend.applyLibraryAction(slot, drop.source.aType, drop.source.aValue, drop.source.aLabel)
            }
        }
        Column {   // drop-slot guide, shown while a drag hovers the knob
            anchors.centerIn: parent; visible: encDrop.containsDrag; z: 5; spacing: 0
            Repeater {
                model: [{t: "◀", z: 0}, {t: "Press", z: 1}, {t: "▶", z: 2}]
                Rectangle {
                    width: enc.width; height: enc.height / 3
                    color: encDrop.zone === modelData.z ? theme.accent : Qt.rgba(0, 0, 0, 0.62)
                    Text { anchors.centerIn: parent; text: modelData.t
                        color: "white"; font.pixelSize: 9; font.bold: true }
                }
            }
        }
        scale: encDrop.containsDrag ? 1.14 : 1.0
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    component RoundBtn: Rectangle {
        property string label: ""
        property bool active: false
        property color activeColor: theme.accent
        property string ctlKey: ""
        property string ledColor: ""
        property bool sel: dv.isSel(ctlKey)
        width: 40; height: 40; radius: 20
        color: sel ? Qt.rgba(theme.ok.r, theme.ok.g, theme.ok.b, 0.22)
             : (active ? Qt.rgba(activeColor.r, activeColor.g, activeColor.b, 0.22)
             : (ledColor !== "" ? ledColor : theme.cell))
        border.color: rbDrop.containsDrag ? theme.accent
                    : (sel ? theme.ok : (active ? activeColor : (ledColor !== "" ? Qt.lighter(ledColor, 1.3) : theme.line)))
        border.width: rbDrop.containsDrag ? 3 : 2
        Text { anchors.centerIn: parent; text: label
            color: (active || sel || ledColor !== "") ? theme.text : theme.muted; font.pixelSize: 11 }
        TapHandler { enabled: ctlKey !== ""; onTapped: backend.selectControl(ctlKey) }
        DropArea {
            id: rbDrop; anchors.fill: parent
            onDropped: (drop) => { if (ctlKey !== "" && drop.source)
                backend.applyLibraryAction(ctlKey, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
        }
        scale: rbDrop.containsDrag ? 1.12 : 1.0
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    component SideCell: Rectangle {
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 30; height: dv.keySize; radius: 6
        color: theme.cell
        border.color: scDrop.containsDrag ? theme.accent
                    : (sel ? theme.ok : (dv.bound(ctlKey) ? theme.accent : theme.line))
        border.width: (sel || scDrop.containsDrag) ? 2 : 1
        clip: true
        Rectangle {   // background fill colour (behind the image)
            anchors.fill: parent; anchors.margins: 1; radius: 5
            visible: dv.bg(ctlKey) !== ""; color: dv.bg(ctlKey) !== "" ? dv.bg(ctlKey) : "transparent"
        }
        Image {
            property var _l: dv.label(ctlKey)
            property bool _shrink: _l ? _l.mode === "shrink" : false
            property bool _top: _l ? _l.pos === "top" : false
            property int _band: _shrink ? dv.shrinkBand(dv.keySize) : 0
            source: dv.img(ctlKey); visible: source != ""
            fillMode: Image.PreserveAspectFit; asynchronous: true
            anchors.fill: parent; anchors.leftMargin: 1; anchors.rightMargin: 1
            anchors.topMargin: (_shrink && _top) ? _band : 1
            anchors.bottomMargin: (_shrink && !_top) ? _band : 1
        }
        CtrlLabel { lbl: dv.label(ctlKey) }
        TapHandler { onTapped: backend.selectControl(ctlKey) }
        DropArea {
            id: scDrop; anchors.fill: parent
            onDropped: (drop) => { if (drop.source)
                backend.applyLibraryAction(ctlKey, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
        }
        Behavior on border.color { ColorAnimation { duration: 130 } }
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
            color: bcHover.hovered ? theme.cell : theme.panel2; border.color: theme.accent
            Behavior on color { ColorAnimation { duration: 120 } }
            Text { id: bc; anchors.centerIn: parent
                text: "← submenu " + backend.menuDepth
                color: theme.accent; font.pixelSize: 11; font.bold: true }
            HoverHandler { id: bcHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: backend.goBack() }
        }

        ColumnLayout {
            id: stack
            anchors.centerIn: parent
            spacing: 26

            // ---- top zone: encoders | strip | grid | strip | encoders ----
            RowLayout {
                id: topZone
                spacing: 14
                // Encoders and side strips come from the backend rather than
                // being written out, so a Live S renders with two dials and no
                // side screens instead of the CT's six and two.
                ColumnLayout {
                    spacing: 20
                    visible: backend.encodersLeft.length > 0
                    Repeater {
                        model: backend.encodersLeft
                        Encoder { ctlKey: modelData; active: dv.encBound(modelData) }
                    }
                }

                // left side strip
                ColumnLayout {
                    spacing: dv.gap
                    visible: backend.sideCellsLeft.length > 0
                    Repeater {
                        model: backend.sideCellsLeft
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
                                Rectangle {   // background fill colour (behind the image)
                                    anchors.fill: parent; anchors.margins: 1; radius: 7
                                    visible: dv.bg(parent.key) !== ""
                                    color: dv.bg(parent.key) !== "" ? dv.bg(parent.key) : "transparent"
                                }
                                Image {
                                    property var _l: dv.label(parent.key)
                                    property bool _shrink: _l ? _l.mode === "shrink" : false
                                    property bool _top: _l ? _l.pos === "top" : false
                                    property int _band: _shrink ? dv.shrinkBand(dv.keySize) : 0
                                    source: parent.src; visible: source != ""
                                    fillMode: Image.PreserveAspectFit; asynchronous: true
                                    anchors.fill: parent; anchors.leftMargin: 1; anchors.rightMargin: 1
                                    anchors.topMargin: (_shrink && _top) ? _band : 1
                                    anchors.bottomMargin: (_shrink && !_top) ? _band : 1
                                }
                                CtrlLabel { lbl: dv.label(parent.key) }
                                Rectangle {  // outline
                                    anchors.fill: parent; anchors.margins: 1; radius: 7
                                    color: "transparent"
                                    border.color: tbDrop.containsDrag ? theme.accent
                                                : (parent.sel ? theme.ok
                                                : (dv.bound(parent.key) ? theme.accent : theme.line))
                                    border.width: (parent.sel || tbDrop.containsDrag) ? 2 : 1
                                    Behavior on border.color { ColorAnimation { duration: 130 } }
                                }
                                Rectangle {  // bound-but-no-image dot
                                    visible: parent.src == "" && dv.bound(parent.key)
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4; color: theme.accent
                                }
                                TapHandler { onTapped: backend.selectControl(parent.key) }
                                DropArea {
                                    id: tbDrop; anchors.fill: parent
                                    onDropped: (drop) => { if (drop.source)
                                        backend.applyLibraryAction(parent.key, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
                                }
                                scale: tbDrop.containsDrag ? 1.06 : 1.0
                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                                Behavior on color { ColorAnimation { duration: 130 } }
                            }
                        }
                    }
                }

                // right side strip
                ColumnLayout {
                    spacing: dv.gap
                    visible: backend.sideCellsRight.length > 0
                    Repeater {
                        model: backend.sideCellsRight
                        SideCell { ctlKey: modelData }
                    }
                }

                ColumnLayout {
                    spacing: 20
                    visible: backend.encodersRight.length > 0
                    Repeater {
                        model: backend.encodersRight
                        Encoder { ctlKey: modelData; active: dv.encBound(modelData) }
                    }
                }
            }

            // ---- workspace round buttons (labelled 1..8 like the hardware) ----
            RowLayout {
                id: wsRow
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                // The first key is the firmware 'circle'; only the label is
                // shifted so the UI reads 1..n like the physical device. A Live
                // S has four of these, a CT and Live eight.
                Repeater {
                    model: backend.workspaceButtons
                    RoundBtn {
                        label: (index + 1).toString()
                        activeColor: theme.ok
                        ctlKey: modelData
                        ledColor: dv.led(modelData)
                        active: backend.selectedWs === modelData
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
                            // save sits in the middle row, keyboard below it;
                            // and fn is the *second* column on this cluster.
                            {l: "save", k: "save"}, {l: "↵", k: "enter"},
                            // "⌨" (U+2328) has no glyph in the UI font and
                            // renders as a box, so this one is spelled out.
                            {l: "kbd", k: "keyboard"}, {l: "fn", k: "fnL"}
                        ]
                        RoundBtn { label: modelData.l; ctlKey: modelData.k
                            active: dv.bound(modelData.k); ledColor: dv.led(modelData.k) }
                    }
                }

                // the big round wheel + dial screen (outer ring = dial, inner = wheel).
                // one drop target spans the whole knob; the band under the cursor
                // picks the slot (Touch → wheel, Press/Rotate → dial).
                Rectangle {
                    width: 180; height: 180; radius: 90
                    color: theme.cell
                    border.color: wheelDrop.containsDrag ? theme.accent
                                : (dv.isSel("dial") ? theme.ok
                                : ((dv.bound("dial") || dv.bound("dial-l") || dv.bound("dial-r")) ? theme.accent : theme.line))
                    border.width: 3
                    scale: wheelDrop.containsDrag ? 1.03 : 1.0
                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                    Behavior on border.color { ColorAnimation { duration: 130 } }
                    TapHandler { onTapped: backend.selectControl("dial") }   // ring selects the dial
                    Rectangle {  // round screen (wheel)
                        anchors.centerIn: parent; width: 150; height: 150; radius: 75
                        color: dv.bg("wheel") !== "" ? dv.bg("wheel") : "#07070a"
                        border.color: dv.isSel("wheel") ? theme.ok
                                    : (dv.bound("wheel") ? theme.accent : theme.line)
                        border.width: dv.isSel("wheel") ? 2 : 1
                        clip: true
                        Behavior on border.color { ColorAnimation { duration: 130 } }
                        TapHandler { onTapped: backend.selectControl("wheel") }
                        // The wheel screen is physically round, so the preview
                        // masks to a circle and fills it. Rectangle.clip only
                        // clips to the bounding box, not the radius, so a plain
                        // clip would still show square corners; and the image
                        // used to be inset to 106px, which drew a small square
                        // floating in a black circle.
                        Item {
                            id: wheelImageArea
                            anchors.fill: parent
                            anchors.margins: 3       // sit inside the bezel
                            visible: dv.img("wheel") != ""
                            layer.enabled: true
                            // Multisampling matters here: without it the mask is
                            // a hard cutout and the circle comes out visibly
                            // stair-stepped.
                            layer.smooth: true
                            layer.samples: 8
                            layer.effect: MultiEffect {
                                maskEnabled: true
                                maskSource: wheelMask
                                // Soften the last fraction of the mask edge so
                                // the rim is not a single hard pixel step.
                                maskThresholdMin: 0.45
                                maskSpreadAtMin: 0.9
                            }
                            Image {
                                anchors.fill: parent
                                source: dv.img("wheel")
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                smooth: true; mipmap: true
                            }
                        }
                        Item {
                            id: wheelMask
                            anchors.fill: wheelImageArea
                            layer.enabled: true
                            layer.smooth: true
                            layer.samples: 8
                            visible: false
                            Rectangle {
                                anchors.fill: parent
                                radius: width / 2
                                color: "black"
                                antialiasing: true
                            }
                        }
                        Text {
                            anchors.centerIn: parent; text: "WHEEL"
                            visible: dv.img("wheel") == "" && dv.label("wheel") === undefined && dv.bg("wheel") === ""
                            color: theme.muted; font.pixelSize: 12; font.letterSpacing: 2
                        }
                        CtrlLabel { lbl: dv.label("wheel") }
                    }
                    DropArea {
                        id: wheelDrop; anchors.fill: parent
                        property int zone: 0   // 0=touch 1=press 2=rotate◀ 3=rotate▶
                        onPositionChanged: (drag) => {
                            zone = Math.max(0, Math.min(3, Math.floor(drag.y / (height / 4)))) }
                        onDropped: (drop) => {
                            if (!drop.source) return
                            var z = Math.max(0, Math.min(3, Math.floor(drop.y / (height / 4))))
                            var slot = z === 0 ? "wheel" : z === 1 ? "dial" : z === 2 ? "dial-l" : "dial-r"
                            backend.applyLibraryAction(slot, drop.source.aType, drop.source.aValue, drop.source.aLabel)
                        }
                    }
                    Column {   // drop-slot guide
                        anchors.centerIn: parent; visible: wheelDrop.containsDrag; z: 10; spacing: 4
                        Repeater {
                            model: [{t: "Touch", z: 0}, {t: "Press", z: 1},
                                    {t: "Rotate ◀", z: 2}, {t: "Rotate ▶", z: 3}]
                            Rectangle {
                                width: 108; height: 30; radius: 15
                                color: wheelDrop.zone === modelData.z ? theme.accent : Qt.rgba(0, 0, 0, 0.72)
                                border.color: theme.accent
                                border.width: wheelDrop.zone === modelData.z ? 0 : 1
                                Text { anchors.centerIn: parent; text: modelData.t
                                    color: "white"; font.pixelSize: 12; font.bold: true }
                            }
                        }
                    }
                }

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model: [
                            {l: "A", k: "a"}, {l: "B", k: "b"}, {l: "C", k: "c"},
                            {l: "D", k: "d"},
                            // and the *first* column on the right cluster
                            {l: "fn", k: "fnR"}, {l: "E", k: "e"}
                        ]
                        RoundBtn { label: modelData.l; ctlKey: modelData.k
                            active: dv.bound(modelData.k); ledColor: dv.led(modelData.k) }
                    }
                }
            }
        }
    }
}
