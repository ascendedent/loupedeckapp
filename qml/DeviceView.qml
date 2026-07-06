import QtQuick
import QtQuick.Layouts

// CT-accurate device mock: 6 encoders, a 4x3 touch-key grid flanked by two
// side strips, a row of round workspace buttons, the CT function buttons, and
// the big round wheel/dial. Slice 1 is static/visual; live mirroring + editing
// wire up next.
Item {
    id: dv
    property var theme
    property int cols: backend.columns
    property int rows: backend.rows

    readonly property int keySize: 74
    readonly property int gap: 8

    implicitWidth: body.width
    implicitHeight: body.height

    // reusable pieces ------------------------------------------------------
    component Encoder: Rectangle {
        width: 54; height: 54; radius: 27
        color: theme.cell; border.color: theme.line; border.width: 3
        Rectangle {  // knob indicator notch
            width: 4; height: 12; radius: 2; color: theme.muted
            anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 6
        }
    }

    component RoundBtn: Rectangle {
        property string label: ""
        property color ring: theme.line
        width: 40; height: 40; radius: 20
        color: theme.cell; border.color: ring; border.width: 2
        Text { anchors.centerIn: parent; text: label; color: theme.muted; font.pixelSize: 11 }
    }

    Rectangle {
        id: body
        width: topZone.width + 48
        height: 40 + topZone.height + 26 + wsRow.height + 26 + wheelZone.height + 40
        radius: 22
        color: "#101016"
        border.color: theme.line; border.width: 1

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 26

            // ---- top zone: encoders | strip | grid | strip | encoders ----
            RowLayout {
                id: topZone
                spacing: 14
                ColumnLayout { spacing: 20; Encoder{} Encoder{} Encoder{} }

                // left side strip (3 cells)
                ColumnLayout {
                    spacing: dv.gap
                    Repeater { model: 3
                        Rectangle { width: 30; height: dv.keySize; radius: 6
                            color: theme.cell; border.color: theme.line } }
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
                                width: dv.keySize; height: dv.keySize; radius: 8
                                color: theme.cell
                                Rectangle { anchors.fill: parent; anchors.margins: 1; radius: 7
                                    color: "transparent"; border.color: theme.line; border.width: 1 }
                            }
                        }
                    }
                }

                // right side strip
                ColumnLayout {
                    spacing: dv.gap
                    Repeater { model: 3
                        Rectangle { width: 30; height: dv.keySize; radius: 6
                            color: theme.cell; border.color: theme.line } }
                }

                ColumnLayout { spacing: 20; Encoder{} Encoder{} Encoder{} }
            }

            // ---- workspace round buttons (circle + 1..7) ----
            RowLayout {
                id: wsRow
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                RoundBtn { label: "○"; ring: theme.ok }
                Repeater { model: 7; RoundBtn { label: (index + 1).toString() } }
            }

            // ---- CT function buttons + big wheel ----
            RowLayout {
                id: wheelZone
                Layout.alignment: Qt.AlignHCenter
                spacing: 28

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    RoundBtn { label: "⌂" }      // home
                    RoundBtn { label: "↺" }      // undo
                    RoundBtn { label: "⌨" }      // keyboard
                    RoundBtn { label: "↵" }      // enter
                    RoundBtn { label: "fn" }     // fnL
                    RoundBtn { label: "▤" }      // save
                }

                // the big round wheel + dial screen
                Rectangle {
                    width: 180; height: 180; radius: 90
                    color: theme.cell; border.color: theme.line; border.width: 3
                    visible: backend.hasWheel
                    Rectangle {  // round screen
                        anchors.centerIn: parent; width: 150; height: 150; radius: 75
                        color: "#07070a"; border.color: theme.line; border.width: 1
                        Text { anchors.centerIn: parent; text: "WHEEL"; color: theme.muted; font.pixelSize: 12; font.letterSpacing: 2 }
                    }
                }

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    RoundBtn { label: "A" }
                    RoundBtn { label: "B" }
                    RoundBtn { label: "C" }
                    RoundBtn { label: "D" }
                    RoundBtn { label: "E" }
                    RoundBtn { label: "fn" }     // fnR
                }
            }
        }
    }
}
