import { useNavigate, useParams } from "react-router-dom";
import { DashboardLayout } from "../components/DashboardLayout";
import { MirrorEditor } from "../components/MirrorEditor";
import { useI18n } from "../context/I18nContext";
import { ArrowLeft } from "lucide-react";

export default function MirrorForm() {
  const { id } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const editing = Boolean(id);

  return (
    <DashboardLayout>
      <div className="p-8 max-w-3xl mx-auto">
        <button onClick={() => navigate("/dashboard")} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={16} /> {t("common.back")}
        </button>
        <h1 className="font-display font-black text-3xl mb-1">{editing ? t("form.edit") : t("form.new")}</h1>
        <p className="text-muted-foreground mb-8">{t("form.subtitle")}</p>
        <MirrorEditor id={id} onSuccess={() => navigate("/dashboard")} />
      </div>
    </DashboardLayout>
  );
}
