// Drawing on Mono: System.Drawing, which Mono backs with libgdiplus.
#if !NETCOREAPP
namespace Loupedeck
{
    using System;
    using System.Drawing;
    using System.Drawing.Drawing2D;
    using System.Drawing.Imaging;
    using System.Drawing.Text;
    using System.IO;

    internal abstract partial class Canvas
    {
        internal static Canvas Create(Int32 width, Int32 height)
        {
            return new GdiCanvas(new Bitmap(width, height, PixelFormat.Format32bppArgb));
        }

        internal static Canvas FromImage(Byte[] bytes) { return new GdiCanvas(Open(bytes)); }

        internal static Int32[] ImageSize(Byte[] bytes)
        {
            using (var b = Open(bytes)) return new[] { b.Width, b.Height };
        }

        internal static Byte[] ToPng(Byte[] bytes)
        {
            using (var b = Open(bytes)) return Save(b);
        }

        internal static Bitmap Open(Byte[] bytes)
        {
            using (var ms = new MemoryStream(bytes))
            using (var img = Image.FromStream(ms))
                return new Bitmap(img);     // copied out so the stream can close
        }

        internal static Byte[] Save(Bitmap b)
        {
            using (var ms = new MemoryStream())
            {
                b.Save(ms, ImageFormat.Png);
                return ms.ToArray();
            }
        }

        internal static Color ToColor(BitmapColor c) { return Color.FromArgb(c.A, c.R, c.G, c.B); }
    }

    internal sealed class GdiCanvas : Canvas
    {
        private readonly Bitmap _bitmap;
        private readonly Graphics _g;

        internal GdiCanvas(Bitmap bitmap)
        {
            this._bitmap = bitmap;
            this._g = Graphics.FromImage(bitmap);
            this._g.SmoothingMode = SmoothingMode.AntiAlias;
            this._g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            this._g.TextRenderingHint = TextRenderingHint.AntiAlias;
        }

        internal override Int32 Width { get { return this._bitmap.Width; } }
        internal override Int32 Height { get { return this._bitmap.Height; } }

        internal override void Clear(BitmapColor color) { this._g.Clear(ToColor(color)); }

        internal override void FillRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color)
        {
            using (var b = new SolidBrush(ToColor(color))) this._g.FillRectangle(b, x, y, w, h);
        }

        internal override void DrawRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color)
        {
            using (var p = new Pen(ToColor(color))) this._g.DrawRectangle(p, x, y, w, h);
        }

        internal override void DrawLine(Int32 x1, Int32 y1, Int32 x2, Int32 y2, BitmapColor color, Single thickness)
        {
            using (var p = new Pen(ToColor(color), thickness)) this._g.DrawLine(p, x1, y1, x2, y2);
        }

        internal override void FillCircle(Int32 x, Int32 y, Int32 radius, BitmapColor color)
        {
            using (var b = new SolidBrush(ToColor(color))) this._g.FillEllipse(b, x - radius, y - radius, radius * 2, radius * 2);
        }

        internal override void DrawImage(Byte[] image, Int32 x, Int32 y, Int32 w, Int32 h, BitmapRotation rotation)
        {
            Bitmap src;
            try { src = Open(image); }
            catch (Exception) { return; }   // SVG and the like: nothing to draw with here
            using (src)
            {
                switch (rotation)
                {
                    case BitmapRotation.Rotate90: src.RotateFlip(RotateFlipType.Rotate90FlipNone); break;
                    case BitmapRotation.Rotate180: src.RotateFlip(RotateFlipType.Rotate180FlipNone); break;
                    case BitmapRotation.Rotate270: src.RotateFlip(RotateFlipType.Rotate270FlipNone); break;
                }
                this._g.DrawImage(src, new Rectangle(x, y, w < 0 ? src.Width : w, h < 0 ? src.Height : h));
            }
        }

        internal override void DrawText(String text, Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color, Int32 size)
        {
            using (var font = new Font(FontFamily.GenericSansSerif, size, FontStyle.Regular, GraphicsUnit.Pixel))
            using (var brush = new SolidBrush(ToColor(color)))
            using (var fmt = new StringFormat())
            {
                fmt.Alignment = StringAlignment.Center;
                fmt.LineAlignment = StringAlignment.Center;
                fmt.Trimming = StringTrimming.EllipsisCharacter;
                this._g.DrawString(text, font, brush, new RectangleF(x, y, w, h), fmt);
            }
        }

        internal override void Translate(Single dx, Single dy) { this._g.TranslateTransform(dx, dy); }

        internal override void ResetMatrix() { this._g.ResetTransform(); }

        internal override Byte[] ToPng() { return Save(this._bitmap); }

        public override void Dispose()
        {
            this._g.Dispose();
            this._bitmap.Dispose();
        }
    }
}
#endif
