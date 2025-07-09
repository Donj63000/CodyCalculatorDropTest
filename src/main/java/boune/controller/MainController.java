package boune.controller;

import javafx.fxml.FXML;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Spinner;
import javafx.scene.control.SpinnerValueFactory;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.image.Image;
import javafx.scene.image.ImageView;
import javafx.scene.layout.BorderPane;
import javafx.util.Duration;
import org.controlsfx.control.Notifications;

public class MainController {
    @FXML private BorderPane root;
    @FXML private ImageView bouneIcon;
    @FXML private TextField tauxField;
    @FXML private Spinner<Integer> ppSpinner;
    @FXML private Button calcBtn;
    @FXML private TextArea resultArea;

    @FXML
    private void initialize() {
        bouneIcon.setImage(new Image(
                "https://static.ankama.com/dofus/www/game/items/200/1244.png"));
        bouneIcon.setPreserveRatio(true);

        ppSpinner.setValueFactory(new SpinnerValueFactory.IntegerSpinnerValueFactory(0, 2000, 100, 10));
        calcBtn.setOnAction(e -> calculer());
    }

    private void calculer() {
        try {
            double tauxBase = Double.parseDouble(tauxField.getText().replace(',', '.')) / 100.0;
            int pp = ppSpinner.getValue();
            double tauxFinal = Math.min(tauxBase * pp / 100.0, 1.0);
            int combats50 = tauxFinal == 1.0 ? 1 : (int)Math.ceil(Math.log(0.5)/Math.log(1 - tauxFinal));
            int combats75 = tauxFinal == 1.0 ? 1 : (int)Math.ceil(Math.log(0.25)/Math.log(1 - tauxFinal));
            int combats90 = tauxFinal == 1.0 ? 1 : (int)Math.ceil(Math.log(0.10)/Math.log(1 - tauxFinal));

            StringBuilder resultat = new StringBuilder();
            resultat.append(String.format("Taux final de drop: %.2f%%\n\n", tauxFinal * 100));
            resultat.append("Combats estimés pour :\n");
            resultat.append(String.format(" - 50%% de chance : %d combats\n", combats50));
            resultat.append(String.format(" - 75%% de chance : %d combats\n", combats75));
            resultat.append(String.format(" - 90%% de chance : %d combats\n", combats90));
            resultArea.setText(resultat.toString());

            Notifications.create()
                .title("Simulation terminée")
                .text(String.format("Taux final : %.2f %%", tauxFinal * 100))
                .position(Pos.TOP_RIGHT)
                .owner(root.getScene().getWindow())
                .hideAfter(Duration.seconds(3))
                .showInformation();
        } catch (Exception ex) {
            resultArea.setText("\u274C Erreur : vérifie tes saisies !");
        }
    }
}
